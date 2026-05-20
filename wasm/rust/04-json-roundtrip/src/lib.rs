// Rust + Spin (SpinKube / WASI P2) – JSON round-trip HTTP component.
//
// Build:  cargo component build --release
// Push:   spin registry push docker.io/abdulaziz7225/json-roundtrip-wasm-rust:latest
// Deploy: kubectl apply -f k8s/04-json-roundtrip/wasm-rust.yaml
//
// Workload: parse a POSTed JSON array of integers, sort it (descending),
// compute count/sum/min/max/mean/median/stdev, re-serialise the response.
// Stresses the serde JSON hot path, allocator churn on small irregular
// objects, and the host->guest HTTP-body copy across the WASI boundary —
// complements 01-prime-sieve (CPU/integer compute), 02-memory-bandwidth
// (bulk memcpy + hashing), and 03-http-fanout (outbound I/O wait).

use serde_json::Value;
use spin_sdk::http::{IncomingRequest, Method, Response};
use spin_sdk::http_component;
use std::time::Instant;

// ── Query helpers ─────────────────────────────────────────────────────────────
fn get_param<'a>(query: &'a str, key: &str) -> Option<&'a str> {
    query
        .split('&')
        .find(|pair| pair.starts_with(key) && pair[key.len()..].starts_with('='))
        .map(|pair| &pair[key.len() + 1..])
}

fn parse_no_list(query: &str) -> bool {
    matches!(get_param(query, "no_list"), Some("true") | Some("1"))
}

// ── Stats ────────────────────────────────────────────────────────────────────
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
    // The same formula is used across all four variants to keep results comparable.
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

// ── Handler ──────────────────────────────────────────────────────────────────
fn jsontx_handler(query: &str, body: &[u8]) -> Response {
    let no_list = parse_no_list(query);

    let start = Instant::now();

    let parsed: Vec<i64> = match serde_json::from_slice::<Value>(body) {
        Ok(Value::Array(arr)) => arr
            .into_iter()
            .filter_map(|v| v.as_i64())
            .collect(),
        _ => {
            return Response::builder()
                .status(400)
                .header("content-type", "text/plain")
                .body("expected JSON array of integers")
                .build();
        }
    };

    let mut sorted = parsed;
    sorted.sort_by(|a, b| b.cmp(a));
    let count = sorted.len();
    let (sum, min, max, mean, median, stdev) = compute_stats(&sorted);

    let elapsed_us = start.elapsed().as_micros();
    eprintln!("jsontx count={count} elapsed_us={elapsed_us}");

    let body_resp = if no_list {
        serde_json::json!({
            "runtime":    "wasm-rust",
            "n":          count,
            "count":      count,
            "sum":        sum,
            "min":        min,
            "max":        max,
            "mean":       mean,
            "median":     median,
            "stdev":      stdev,
            "elapsed_us": elapsed_us,
        })
    } else {
        serde_json::json!({
            "runtime":    "wasm-rust",
            "n":          count,
            "count":      count,
            "sum":        sum,
            "min":        min,
            "max":        max,
            "mean":       mean,
            "median":     median,
            "stdev":      stdev,
            "elapsed_us": elapsed_us,
            "sorted":     sorted,
        })
    }
    .to_string();

    Response::builder()
        .status(200)
        .header("content-type", "application/json")
        .body(body_resp)
        .build()
}

fn health_handler() -> Response {
    Response::builder()
        .status(200)
        .header("content-type", "text/plain")
        .body("")
        .build()
}

// ── Entry point ───────────────────────────────────────────────────────────────
#[http_component]
async fn handle(req: IncomingRequest) -> Response {
    let method = req.method();
    let path_with_query = req.path_with_query().unwrap_or_default();
    let (path, query) = match path_with_query.find('?') {
        Some(i) => (path_with_query[..i].to_string(), path_with_query[i + 1..].to_string()),
        None    => (path_with_query.clone(), String::new()),
    };

    if path == "/health" && matches!(method, Method::Get) {
        return health_handler();
    }

    if path == "/jsontx" && matches!(method, Method::Post) {
        let body = req.into_body().await.unwrap_or_default();
        return jsontx_handler(&query, &body);
    }

    Response::builder()
        .status(404)
        .header("content-type", "text/plain")
        .body("not found")
        .build()
}
