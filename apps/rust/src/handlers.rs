use std::sync::Arc;

use axum::body::Bytes;
use axum::extract::rejection::{BytesRejection, QueryRejection};
use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::response::Response;
use axum::routing::{get, post};
use axum::Router;
use sqlx::PgPool;

use crate::models::{Inserted, ListResponse, Reading, StatsResponse};
use crate::respond::{send, send_json, ApiError, HEALTH};
use crate::{sql, validate};

type Pairs = Result<Query<Vec<(String, String)>>, QueryRejection>;
type Body = Result<Bytes, BytesRejection>;
type Resp = Result<Response, ApiError>;

pub fn router(pool: PgPool, jwt_secret: Option<Vec<u8>>) -> Router {
    let mut api = Router::new()
        .route("/readings/stats", get(stats))
        .route("/readings/{id}", get(get_reading))
        .route("/readings", get(list).post(create))
        .route("/readings/batch", post(create_batch));
    // route_layer only wraps the routes above, so /health stays public and unknown routes stay 404.
    if let Some(secret) = jwt_secret {
        api = api.route_layer(axum::middleware::from_fn_with_state(Arc::new(secret), crate::auth::jwt_auth));
    }
    Router::new()
        .route("/health", get(|| async { send(StatusCode::OK, HEALTH.to_vec()) })) // no DB access
        .merge(api)
        .fallback(|| async { ApiError::NotFound })
        .method_not_allowed_fallback(|| async { ApiError::NotFound })
        .layer(axum::extract::DefaultBodyLimit::max(1024 * 1024))
        .with_state(pool)
}

async fn get_reading(State(pool): State<PgPool>, id: Result<Path<String>, axum::extract::rejection::PathRejection>) -> Resp {
    let id = validate::parse_id(&id.map_err(|_| ApiError::Invalid)?.0)?;
    let row = sqlx::query(sql::BY_ID).bind(id).fetch_optional(&pool).await?;
    let row = row.ok_or(ApiError::NotFound)?;
    send_json(StatusCode::OK, &Reading::from_row(&row)?)
}

async fn list(State(pool): State<PgPool>, q: Pairs) -> Resp {
    let q = q.map_err(|_| ApiError::Invalid)?.0;
    let range = validate::parse_device_range(&q)?;
    let (limit, offset) = validate::parse_paging(&q)?;
    let rows = sqlx::query(sql::LIST)
        .bind(range.device)
        .bind(range.from)
        .bind(range.to)
        .bind(limit)
        .bind(offset)
        .fetch_all(&pool)
        .await?;
    let items = rows.iter().map(Reading::from_row).collect::<Result<Vec<_>, _>>()?;
    send_json(StatusCode::OK, &ListResponse { items, limit, offset })
}

async fn stats(State(pool): State<PgPool>, q: Pairs) -> Resp {
    let q = q.map_err(|_| ApiError::Invalid)?.0;
    let range = validate::parse_device_range(&q)?;
    let row = sqlx::query(sql::STATS)
        .bind(range.device)
        .bind(range.from)
        .bind(range.to)
        .fetch_one(&pool)
        .await?;
    send_json(StatusCode::OK, &StatsResponse::from_row(range.device, &row)?)
}

async fn create(State(pool): State<PgPool>, body: Body) -> Resp {
    let json = validate::parse_json(&body.map_err(|_| ApiError::BadRequest)?)?;
    let r = validate::new_reading(&json).ok_or(ApiError::Invalid)?;
    let row = sqlx::query(sql::INSERT)
        .bind(r.device_id)
        .bind(r.temperature_centi)
        .bind(r.humidity_bp)
        .bind(r.observed_at)
        .fetch_one(&pool)
        .await?;
    send_json(StatusCode::CREATED, &Reading::from_row(&row)?)
}

async fn create_batch(State(pool): State<PgPool>, body: Body) -> Resp {
    let json = validate::parse_json(&body.map_err(|_| ApiError::BadRequest)?)?;
    if !json.is_object() {
        return Err(ApiError::BadRequest);
    }
    let items = validate::batch(&json).ok_or(ApiError::Invalid)?;
    let mut q = sqlx::query(sql::batch_insert(items.len()));
    for r in &items {
        q = q.bind(r.device_id).bind(r.temperature_centi).bind(r.humidity_bp).bind(r.observed_at);
    }
    q.execute(&pool).await?;
    send_json(StatusCode::CREATED, &Inserted { inserted: items.len() })
}
