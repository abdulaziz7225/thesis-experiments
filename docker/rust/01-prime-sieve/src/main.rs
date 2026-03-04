use axum::{
    extract::Query,
    http::StatusCode,
    response::Json,
    routing::get,
    Router,
};
use serde::{Deserialize, Serialize};
use std::time::Instant;
use tracing::info;

// ── Query params ────────────────────────────────────────────────────────────
#[derive(Deserialize)]
struct SieveParams {
    /// Upper bound (inclusive). Capped at 10 000 000.
    limit: Option<u64>,
    /// When non-zero, the `primes` array is omitted from the response
    /// to avoid serialisation overhead during throughput benchmarks.
    /// Accepts "0" or "1" (serde_urlencoded rejects bool "true"/"false" strings).
    #[serde(default)]
    no_list: Option<u8>,
}

// ── Response ────────────────────────────────────────────────────────────────
#[derive(Serialize)]
struct SieveResponse {
    runtime:    &'static str,
    limit:      u64,
    count:      usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    primes:     Option<Vec<u64>>,
    elapsed_us: u128,
}

// ── Algorithm ───────────────────────────────────────────────────────────────
/// Classic Sieve of Eratosthenes.
/// Returns every prime p where 2 ≤ p ≤ limit.
fn sieve_of_eratosthenes(limit: u64) -> Vec<u64> {
    if limit < 2 {
        return vec![];
    }
    let n = (limit + 1) as usize;
    let mut is_prime = vec![true; n];
    is_prime[0] = false;
    is_prime[1] = false;

    let mut i = 2usize;
    while i * i <= limit as usize {
        if is_prime[i] {
            let mut j = i * i;
            while j < n {
                is_prime[j] = false;
                j += i;
            }
        }
        i += 1;
    }

    is_prime
        .iter()
        .enumerate()
        .filter_map(|(idx, &p)| if p { Some(idx as u64) } else { None })
        .collect()
}

// ── Handlers ────────────────────────────────────────────────────────────────
async fn sieve_handler(Query(params): Query<SieveParams>) -> Json<SieveResponse> {
    let limit = params.limit.unwrap_or(10_000).min(10_000_000);

    let start  = Instant::now();
    let primes = sieve_of_eratosthenes(limit);
    let elapsed_us = start.elapsed().as_micros();

    let count = primes.len();
    info!(limit, count, elapsed_us, "sieve completed");

    Json(SieveResponse {
        runtime:    "rust-docker",
        limit,
        count,
        primes:     (params.no_list.unwrap_or(0) == 0).then_some(primes),
        elapsed_us,
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
                .add_directive("prime_sieve=info".parse().unwrap()),
        )
        .json()
        .init();

    let app = Router::new()
        .route("/sieve",  get(sieve_handler))
        .route("/health", get(health_handler));

    let addr = "0.0.0.0:8080";
    info!("listening on {addr}");
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
