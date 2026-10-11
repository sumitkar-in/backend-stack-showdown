mod auth;
mod config;
mod db;
mod handlers;
mod models;
mod respond;
mod sql;
mod validate;

use std::time::Duration;

use axum::serve::ListenerExt;
use tokio::net::TcpListener;
use tokio::signal::unix::{signal, SignalKind};

fn main() {
    let cfg = config::Config::load().unwrap_or_else(|e| {
        eprintln!("{e}");
        std::process::exit(1);
    });
    let rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(cfg.worker_threads)
        .enable_all()
        .build()
        .expect("runtime");
    if let Err(e) = rt.block_on(run(cfg)) {
        eprintln!("fatal: {e}");
        std::process::exit(1);
    }
}

async fn run(cfg: config::Config) -> Result<(), Box<dyn std::error::Error>> {
    let pool = db::connect(&cfg).await?;
    let listener = TcpListener::bind(("0.0.0.0", cfg.port))
        .await?
        .tap_io(|tcp| {
            let _ = tcp.set_nodelay(true); // same as Go/Node/uvicorn defaults
        });

    let serve = axum::serve(listener, handlers::router(pool.clone(), cfg.jwt_secret.clone())).with_graceful_shutdown(shutdown());
    // Give in-flight requests at most 10 s after SIGTERM.
    let mut term = signal(SignalKind::terminate())?;
    tokio::select! {
        r = serve => r?,
        _ = async { term.recv().await; tokio::time::sleep(Duration::from_secs(10)).await } => {}
    }
    pool.close().await;
    Ok(())
}

async fn shutdown() {
    let mut term = signal(SignalKind::terminate()).expect("SIGTERM handler");
    let mut int = signal(SignalKind::interrupt()).expect("SIGINT handler");
    tokio::select! { _ = term.recv() => {}, _ = int.recv() => {} }
}
