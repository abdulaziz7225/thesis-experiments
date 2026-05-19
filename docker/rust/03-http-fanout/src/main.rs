// Rust + Docker (runc) — HTTP fan-out HTTP service (I/O-bound experiment).
//
// On each inbound request, dispatch N concurrent outbound HTTP GETs to the
// in-cluster `io-echo` backend; the backend sleeps for delay_ms before
// responding, so the handler is dominated by outbound I/O wait rather than
// CPU work. Concurrent outbound is via `futures::future::join_all` over a
// shared `reqwest::Client` — the idiomatic Rust async I/O pattern.
//
// This is the docker-runc counterpart to the wasm-rust Spin component; they
// expose the same /fanout HTTP API to keep the comparison apples-to-apples.

use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::Json,
    routing::get,
    Router,
};
use futures::future::join_all;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::Instant;
use tracing::info;

const BACKEND_URL: &str = "http://io-echo.http-fanout.svc.cluster.local/echo";

const DEFAULT_N: usize = 5;
const MAX_N: usize = 20;
const DEFAULT_DELAY_MS: u64 = 50;
const MAX_DELAY_MS: u64 = 1000;

// ── Query params ─────────────────────────────────────────────────────────────
#[derive(Deserialize)]
struct FanoutParams {
    n: Option<usize>,
    delay_ms: Option<u64>,
    #[serde(default)]
    no_list: Option<u8>,
}

// ── Response ─────────────────────────────────────────────────────────────────
#[derive(Serialize)]
struct FanoutResponse {
    runtime:    &'static str,
    n:          usize,
    delay_ms:   u64,
    ok_count:   usize,
    err_count:  usize,
    elapsed_us: u128,
    #[serde(skip_serializing_if = "Option::is_none")]
    responses:  Option<Vec<u16>>,
}

// ── Handler (I/O-bound fan-out) ──────────────────────────────────────────────
async fn fanout_handler(
    State(client): State<Arc<reqwest::Client>>,
    Query(params): Query<FanoutParams>,
) -> Json<FanoutResponse> {
    let n = params.n.unwrap_or(DEFAULT_N).clamp(1, MAX_N);
    let delay_ms = params.delay_ms.unwrap_or(DEFAULT_DELAY_MS).min(MAX_DELAY_MS);
    let no_list = params.no_list.unwrap_or(0) != 0;

    let url = format!("{BACKEND_URL}?delay_ms={delay_ms}&size_b=256");

    let start = Instant::now();

    let futures_iter = (0..n).map(|_| {
        let client = client.clone();
        let url = url.clone();
        async move { client.get(&url).send().await }
    });
    let results = join_all(futures_iter).await;

    let mut ok_count = 0usize;
    let mut err_count = 0usize;
    let mut statuses: Vec<u16> = Vec::with_capacity(n);
    for r in &results {
        match r {
            Ok(resp) => {
                let s = resp.status().as_u16();
                statuses.push(s);
                if (200..300).contains(&s) {
                    ok_count += 1;
                } else {
                    err_count += 1;
                }
            }
            Err(_) => {
                err_count += 1;
                statuses.push(0);
            }
        }
    }

    let elapsed_us = start.elapsed().as_micros();
    info!(n, delay_ms, elapsed_us, ok_count, err_count, "fanout completed");

    Json(FanoutResponse {
        runtime:    "rust-docker",
        n,
        delay_ms,
        ok_count,
        err_count,
        elapsed_us,
        responses:  if no_list { None } else { Some(statuses) },
    })
}

async fn health_handler() -> StatusCode {
    StatusCode::OK
}

// ── Entry point ──────────────────────────────────────────────────────────────
#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("http_fanout=info".parse().unwrap()),
        )
        .json()
        .init();

    let client = Arc::new(
        reqwest::Client::builder()
            .pool_max_idle_per_host(64)
            .build()
            .expect("reqwest client"),
    );

    let app = Router::new()
        .route("/fanout", get(fanout_handler))
        .route("/health", get(health_handler))
        .with_state(client);

    let addr = "0.0.0.0:8080";
    info!("listening on {addr}");
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
