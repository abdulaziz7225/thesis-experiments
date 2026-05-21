use axum::{
    extract::Query,
    http::StatusCode,
    response::Json,
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use std::time::Instant;
use tracing::info;

#[derive(Deserialize)]
struct JsonTxParams {
    #[serde(default)]
    no_list: Option<u8>,
}

#[derive(Serialize)]
struct JsonTxResponse {
    runtime:    &'static str,
    n:          usize,
    count:      usize,
    sum:        i64,
    min:        i64,
    max:        i64,
    mean:       f64,
    median:     i64,
    stdev:      f64,
    elapsed_us: u128,
    #[serde(skip_serializing_if = "Option::is_none")]
    sorted:     Option<Vec<i64>>,
}

fn compute_stats(sorted_desc: &[i64]) -> (i64, i64, i64, f64, i64, f64) {
    let count = sorted_desc.len();
    if count == 0 {
        return (0, 0, 0, 0.0, 0, 0.0);
    }
    let sum: i64 = sorted_desc.iter().sum();
    let max = sorted_desc[0];
    let min = sorted_desc[count - 1];
    let mean = sum as f64 / count as f64;
    // Median definition: descending-sort, then arr[(n-1)/2] (mid-low for even N).
    // Same formula across all four variants to keep results comparable.
    let median = sorted_desc[(count - 1) / 2];
    let variance: f64 = sorted_desc
        .iter()
        .map(|x| {
            let d = *x as f64 - mean;
            d * d
        })
        .sum::<f64>()
        / count as f64;
    let stdev = variance.sqrt();
    (sum, min, max, mean, median, stdev)
}

async fn jsontx_handler(
    Query(params): Query<JsonTxParams>,
    Json(parsed): Json<Vec<i64>>,
) -> Result<Json<JsonTxResponse>, StatusCode> {
    let no_list = params.no_list.unwrap_or(0) != 0;

    let start = Instant::now();

    let mut sorted = parsed;
    sorted.sort_by(|a, b| b.cmp(a));
    let count = sorted.len();
    let (sum, min, max, mean, median, stdev) = compute_stats(&sorted);

    let elapsed_us = start.elapsed().as_micros();
    info!(count, elapsed_us, "jsontx completed");

    Ok(Json(JsonTxResponse {
        runtime: "rust-docker",
        n: count,
        count,
        sum,
        min,
        max,
        mean,
        median,
        stdev,
        elapsed_us,
        sorted: if no_list { None } else { Some(sorted) },
    }))
}

async fn health_handler() -> StatusCode {
    StatusCode::OK
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("json_roundtrip=info".parse().unwrap()),
        )
        .json()
        .init();

    let app = Router::new()
        .route("/jsontx", post(jsontx_handler))
        .route("/health", get(health_handler))
        // Increase the default request body limit so large N (up to ~100k integers)
        // round-trips cleanly. axum defaults to 2 MiB; 16 MiB is comfortably above
        // a 100k integer array serialised as JSON.
        .layer(axum::extract::DefaultBodyLimit::max(16 * 1024 * 1024));

    let addr = "0.0.0.0:8080";
    info!("listening on {addr}");
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
