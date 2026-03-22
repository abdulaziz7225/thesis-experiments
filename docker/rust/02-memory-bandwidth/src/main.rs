use axum::{
    extract::Query,
    http::StatusCode,
    response::Json,
    routing::get,
    Router,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::time::Instant;
use tracing::info;

// ── Query params ─────────────────────────────────────────────────────────────
#[derive(Deserialize)]
struct MemBwParams {
    /// Buffer size in kilobytes. Default 64, max 10240.
    size_kb: Option<usize>,
    /// When non-zero, skips SHA-256 hashing (measures raw allocation cost).
    #[serde(default)]
    no_hash: Option<u8>,
}

// ── Response ─────────────────────────────────────────────────────────────────
#[derive(Serialize)]
struct MemBwResponse {
    runtime:    &'static str,
    size_kb:    usize,
    sha256:     String,
    elapsed_us: u128,
}

// ── Handler ───────────────────────────────────────────────────────────────────
async fn membw_handler(Query(params): Query<MemBwParams>) -> Json<MemBwResponse> {
    let size_kb = params.size_kb.unwrap_or(64).min(10240);
    let no_hash = params.no_hash.unwrap_or(0) != 0;
    let size_bytes = size_kb * 1024;

    let start = Instant::now();

    // Allocate and fill buffer with deterministic pattern.
    let buf: Vec<u8> = (0..size_bytes).map(|i| (i & 0xFF) as u8).collect();

    let sha256 = if no_hash {
        String::new()
    } else {
        let mut hasher = Sha256::new();
        hasher.update(&buf);
        hex::encode(hasher.finalize())
    };

    let elapsed_us = start.elapsed().as_micros();
    info!(size_kb, elapsed_us, "membw completed");

    Json(MemBwResponse {
        runtime: "rust-docker",
        size_kb,
        sha256,
        elapsed_us,
    })
}

async fn health_handler() -> StatusCode {
    StatusCode::OK
}

// ── Entry point ───────────────────────────────────────────────────────────────
#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("memory_bandwidth=info".parse().unwrap()),
        )
        .json()
        .init();

    let app = Router::new()
        .route("/membw",     get(membw_handler))
        .route("/health", get(health_handler));

    let addr = "0.0.0.0:8080";
    info!("listening on {addr}");
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
