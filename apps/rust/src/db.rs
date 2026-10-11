use std::time::Duration;

use sqlx::postgres::{PgConnectOptions, PgPoolOptions};
use sqlx::PgPool;

use crate::config::Config;

/// Fixed-size pool (min == max) with every connection opened before serving.
pub async fn connect(cfg: &Config) -> Result<PgPool, sqlx::Error> {
    let opts = PgConnectOptions::new()
        .host(&cfg.db_host)
        .port(cfg.db_port)
        .username(&cfg.db_user)
        .password(&cfg.db_password)
        .database(&cfg.db_name);

    let pool = PgPoolOptions::new()
        .min_connections(cfg.pool_size)
        .max_connections(cfg.pool_size)
        .acquire_timeout(Duration::from_secs(10))
        .test_before_acquire(false) // default pings (an extra round trip) on every acquire
        .idle_timeout(None)
        .max_lifetime(None)
        .connect_with(opts)
        .await?;

    // Acquire all connections at once so none are opened lazily under load.
    let tasks: Vec<_> = (0..cfg.pool_size)
        .map(|_| {
            let pool = pool.clone();
            tokio::spawn(async move { pool.acquire().await.map(drop) })
        })
        .collect();
    for t in tasks {
        t.await.map_err(|e| sqlx::Error::Protocol(e.to_string()))??;
    }
    Ok(pool)
}
