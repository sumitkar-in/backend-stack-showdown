use std::env;

pub struct Config {
    pub port: u16,
    pub pool_size: u32,
    pub worker_threads: usize,
    pub db_host: String,
    pub db_port: u16,
    pub db_name: String,
    pub db_user: String,
    pub db_password: String,
    /// Some(secret) when AUTH_MODE=jwt
    pub jwt_secret: Option<Vec<u8>>,
}

fn var(key: &str, default: &str) -> String {
    env::var(key).ok().filter(|v| !v.is_empty()).unwrap_or_else(|| default.to_string())
}

impl Config {
    pub fn load() -> Result<Self, String> {
        let num = |k: &str, d: &str| var(k, d).parse::<u32>().map_err(|_| format!("invalid {k}"));
        Ok(Self {
            port: num("PORT", "8080")? as u16,
            pool_size: num("DB_POOL_TOTAL", "20")?,
            worker_threads: num("TOKIO_WORKER_THREADS", "2")? as usize,
            db_host: var("DB_HOST", "postgres"),
            db_port: num("DB_PORT", "5432")? as u16,
            db_name: var("DB_NAME", "sensorpulse"),
            db_user: var("DB_USER", "bench"),
            db_password: var("DB_PASSWORD", ""),
            jwt_secret: (var("AUTH_MODE", "none") == "jwt")
                .then(|| var("JWT_SECRET", "bench-jwt-secret-local-only").into_bytes()),
        })
    }
}
