use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::extract::{Request, State};
use axum::http::{header, HeaderValue, StatusCode};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use hmac::{Hmac, Mac};
use serde_json::Value;
use sha2::Sha256;

use crate::respond::send;

/// Verifies an HS256 bearer token on every request (no caching of verified tokens).
/// Rules (identical in all stacks): "Bearer " prefix, three non-empty segments, header alg == HS256,
/// valid HMAC-SHA256 signature, integer exp in the future, non-empty sub.
pub async fn jwt_auth(State(secret): State<Arc<Vec<u8>>>, req: Request, next: Next) -> Response {
    let header = req.headers().get(header::AUTHORIZATION).and_then(|v| v.to_str().ok());
    if verify(header, &secret) {
        return next.run(req).await;
    }
    let mut resp = send(StatusCode::UNAUTHORIZED, br#"{"error":"unauthorized"}"#.to_vec()).into_response();
    resp.headers_mut().insert(header::WWW_AUTHENTICATE, HeaderValue::from_static("Bearer"));
    resp
}

fn verify(header: Option<&str>, secret: &[u8]) -> bool {
    let Some(tok) = header.and_then(|h| h.strip_prefix("Bearer ")) else {
        return false;
    };
    let mut parts = tok.split('.');
    let (Some(h), Some(p), Some(s), None) = (parts.next(), parts.next(), parts.next(), parts.next()) else {
        return false;
    };
    if h.is_empty() || p.is_empty() || s.is_empty() {
        return false;
    }
    let Ok(sig) = URL_SAFE_NO_PAD.decode(s) else { return false };
    let Ok(mut mac) = Hmac::<Sha256>::new_from_slice(secret) else { return false };
    mac.update(h.as_bytes());
    mac.update(b".");
    mac.update(p.as_bytes());
    if mac.verify_slice(&sig).is_err() {
        return false; // constant-time comparison
    }
    let Ok(hb) = URL_SAFE_NO_PAD.decode(h) else { return false };
    let Ok(hdr) = serde_json::from_slice::<Value>(&hb) else { return false };
    if hdr.get("alg").and_then(Value::as_str) != Some("HS256") {
        return false;
    }
    let Ok(pb) = URL_SAFE_NO_PAD.decode(p) else { return false };
    let Ok(claims) = serde_json::from_slice::<Value>(&pb) else { return false };
    let sub_ok = claims.get("sub").and_then(Value::as_str).is_some_and(|s| !s.is_empty());
    let now = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs() as i64).unwrap_or(0);
    // as_i64 is None for a float exp (e.g. 1700000000.5) => rejected
    let exp_ok = claims.get("exp").and_then(Value::as_i64).is_some_and(|e| e > now);
    sub_ok && exp_ok
}
