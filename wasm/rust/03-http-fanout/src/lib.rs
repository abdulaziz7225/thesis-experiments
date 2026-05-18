// Rust + Spin (SpinKube / WASI P2) – HTTP fan-out HTTP component (I/O-bound experiment).
//
// Build:  cargo component build --release
// Push:   spin registry push docker.io/abdulaziz7225/http-fanout-wasm-rust:latest
// Deploy: kubectl apply -f k8s/03-http-fanout/wasm-rust.yaml
//
// Workload (I/O-bound): on each inbound request, dispatch N outbound HTTP GETs
// concurrently to the in-cluster `io-echo` backend. The backend sleeps for
// `delay_ms` before responding, so the inbound handler is dominated by outbound
// I/O wait rather than CPU work. This complements the CPU-bound (01-prime-sieve)
// and memory-bound (02-memory-bandwidth) experiments. Concurrency is achieved
// with `futures::future::join_all`, the idiomatic Spin Rust pattern for
// concurrent outbound HTTP in a WASI P2 component (a single Wasmtime instance
// drives the futures cooperatively).

use futures::future::join_all;
use spin_sdk::http::{IncomingRequest, Method, Request, Response};
use spin_sdk::http_component;
use std::time::Instant;

const BACKEND_URL: &str = "http://io-echo.http-fanout.svc.cluster.local/echo";

const DEFAULT_N: usize = 5;
const MAX_N: usize = 20;
const DEFAULT_DELAY_MS: u64 = 50;
const MAX_DELAY_MS: u64 = 1000;

// ── Query helpers ─────────────────────────────────────────────────────────────
fn get_param<'a>(query: &'a str, key: &str) -> Option<&'a str> {
    query
        .split('&')
        .find(|pair| pair.starts_with(key) && pair[key.len()..].starts_with('='))
        .map(|pair| &pair[key.len() + 1..])
}

fn parse_n(query: &str) -> usize {
    get_param(query, "n")
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(DEFAULT_N)
        .clamp(1, MAX_N)
}

fn parse_delay_ms(query: &str) -> u64 {
    get_param(query, "delay_ms")
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(DEFAULT_DELAY_MS)
        .min(MAX_DELAY_MS)
}

fn parse_no_list(query: &str) -> bool {
    matches!(get_param(query, "no_list"), Some("true") | Some("1"))
}

// ── Handler (I/O-bound fan-out) ──────────────────────────────────────────────
async fn fanout_handler(query: &str) -> Response {
    let n = parse_n(query);
    let delay_ms = parse_delay_ms(query);
    let no_list = parse_no_list(query);

    let url = format!("{BACKEND_URL}?delay_ms={delay_ms}&size_b=256");

    let start = Instant::now();

    // Concurrent outbound HTTP — N futures driven by the Wasmtime reactor.
    let futures_iter = (0..n).map(|_| {
        let req = Request::builder()
            .method(Method::Get)
            .uri(&url)
            .build();
        async move { spin_sdk::http::send::<_, Response>(req).await }
    });
    let results: Vec<_> = join_all(futures_iter).await;

    let mut ok_count = 0usize;
    let mut err_count = 0usize;
    let mut statuses: Vec<u16> = Vec::with_capacity(n);
    for r in &results {
        match r {
            Ok(resp) => {
                let s = *resp.status();
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
    eprintln!("fanout n={n} delay_ms={delay_ms} elapsed_us={elapsed_us} ok={ok_count} err={err_count}");

    let body = if no_list {
        serde_json::json!({
            "runtime":    "wasm-rust",
            "n":          n,
            "delay_ms":   delay_ms,
            "ok_count":   ok_count,
            "err_count":  err_count,
            "elapsed_us": elapsed_us,
        })
    } else {
        serde_json::json!({
            "runtime":    "wasm-rust",
            "n":          n,
            "delay_ms":   delay_ms,
            "ok_count":   ok_count,
            "err_count":  err_count,
            "elapsed_us": elapsed_us,
            "responses":  statuses,
        })
    }
    .to_string();

    Response::builder()
        .status(200)
        .header("content-type", "application/json")
        .body(body)
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
    let path_with_query = req.path_with_query().unwrap_or_default();
    let (path, query) = match path_with_query.find('?') {
        Some(i) => (&path_with_query[..i], &path_with_query[i + 1..]),
        None    => (path_with_query.as_str(), ""),
    };

    match path {
        "/fanout" => fanout_handler(query).await,
        "/health" => health_handler(),
        _         => Response::builder().status(404).body("not found").build(),
    }
}
