// Rust + Spin (SpinKube / WASI P2) – memory-bandwidth HTTP component
//
// Build:  cargo component build --release
// Push:   spin registry push docker.io/abdulaziz7225/memory-bandwidth-wasm-rust:latest
// Deploy: kubectl apply -f k8s/02-memory-bandwidth/wasm-rust.yaml
//
// Workload: allocate a byte buffer of configurable size (default 64 KB),
// fill with deterministic pattern, compute SHA-256 hash, return result.
// This tests memory allocation throughput under WASI P2 rather than filesystem I/O
// (SpinKube sandboxes do not expose writable /tmp by default).

use spin_sdk::http::{IncomingRequest, Response};
use spin_sdk::http_component;
use sha2::{Digest, Sha256};
use std::time::Instant;

// ── Query helpers ─────────────────────────────────────────────────────────────
fn get_param<'a>(query: &'a str, key: &str) -> Option<&'a str> {
    query
        .split('&')
        .find(|pair| pair.starts_with(key) && pair[key.len()..].starts_with('='))
        .map(|pair| &pair[key.len() + 1..])
}

fn parse_size_kb(query: &str) -> usize {
    get_param(query, "size_kb")
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(64)
        .min(10240)
}

fn parse_no_hash(query: &str) -> bool {
    matches!(get_param(query, "no_hash"), Some("true") | Some("1"))
}

// ── Handler ───────────────────────────────────────────────────────────────────
fn membw_handler(query: &str) -> Response {
    let size_kb = parse_size_kb(query);
    let no_hash = parse_no_hash(query);
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
    eprintln!("membw size_kb={size_kb} elapsed_us={elapsed_us}");

    let body = serde_json::json!({
        "runtime":    "wasm-rust",
        "size_kb":    size_kb,
        "sha256":     sha256,
        "elapsed_us": elapsed_us,
    })
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
fn handle(req: IncomingRequest) -> Response {
    let path_with_query = req.path_with_query().unwrap_or_default();
    let (path, query) = match path_with_query.find('?') {
        Some(i) => (&path_with_query[..i], &path_with_query[i + 1..]),
        None    => (path_with_query.as_str(), ""),
    };

    match path {
        "/membw"     => membw_handler(query),
        "/health" => health_handler(),
        _         => Response::builder().status(404).body("not found").build(),
    }
}
