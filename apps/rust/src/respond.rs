use axum::http::{header, StatusCode};
use axum::response::{IntoResponse, Response};
use serde::Serialize;

pub const HEALTH: &[u8] = br#"{"status":"ok"}"#;

#[derive(Debug)]
pub enum ApiError {
    BadRequest,
    Invalid,
    NotFound,
    Internal,
}

pub fn send(status: StatusCode, body: Vec<u8>) -> Response {
    (status, [(header::CONTENT_TYPE, "application/json")], body).into_response()
}

pub fn send_json<T: Serialize>(status: StatusCode, value: &T) -> Result<Response, ApiError> {
    serde_json::to_vec(value)
        .map(|b| send(status, b))
        .map_err(|_| ApiError::Internal)
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, body): (_, &[u8]) = match self {
            ApiError::BadRequest => (StatusCode::BAD_REQUEST, br#"{"error":"bad_request"}"#),
            ApiError::Invalid => (StatusCode::UNPROCESSABLE_ENTITY, br#"{"error":"validation_error"}"#),
            ApiError::NotFound => (StatusCode::NOT_FOUND, br#"{"error":"not_found"}"#),
            ApiError::Internal => (StatusCode::INTERNAL_SERVER_ERROR, br#"{"error":"internal"}"#),
        };
        send(status, body.to_vec())
    }
}

impl From<sqlx::Error> for ApiError {
    /// FK (23503) / CHECK (23514) violations -> 422, everything else -> 500.
    fn from(e: sqlx::Error) -> Self {
        match e.as_database_error().and_then(|d| d.code()).as_deref() {
            Some("23503") | Some("23514") => ApiError::Invalid,
            _ => ApiError::Internal,
        }
    }
}
