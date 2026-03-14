// Rust + Spin (SpinKube / WASI P2) – prime-sieve HTTP component
//
// Build:  cargo component build --release
// Push:   spin registry push docker.io/abdulaziz7225/prime-sieve-wasm-rust:latest
// Deploy: kubectl apply -f k8s/01-prime-sieve/wasm-rust.yaml
//
// Key differences from wasm/wasmedge/rust/01-prime-sieve (WASI P1 archive):
//   - Runtime:  Wasmtime/Cranelift (via Spin)  vs  WasmEdge/LLVM
//   - WASI:     Preview 2 (Component Model)    vs  Preview 1 (snapshot_preview1)
//   - HTTP:     wasi:http/incoming-handler      vs  wasmedge_wasi_socket TCP loop
//   - Threading: request-scoped, no server loop vs  single-threaded accept() loop
//   - runtime field in JSON: "wasm-rust"

use spin_sdk::http::{IncomingRequest, Response};
use spin_sdk::http_component;
use std::time::Instant;

// ── Algorithm ────────────────────────────────────────────────────────────────
// Identical to docker/rust and wasm/rust variants — algorithm is not the variable.
fn sieve_of_eratosthenes(limit: usize) -> Vec<usize> {
    if limit < 2 {
        return vec![];
    }
    let mut is_prime = vec![true; limit + 1];
    is_prime[0] = false;
    is_prime[1] = false;

    let mut i = 2usize;
    while i * i <= limit {
        if is_prime[i] {
            let mut j = i * i;
            while j <= limit {
                is_prime[j] = false;
                j += i;
            }
        }
        i += 1;
    }

    is_prime
        .iter()
        .enumerate()
        .filter_map(|(idx, &p)| if p { Some(idx) } else { None })
        .collect()
}

// ── Query helpers ─────────────────────────────────────────────────────────────
fn get_param<'a>(query: &'a str, key: &str) -> Option<&'a str> {
    query
        .split('&')
        .find(|pair| pair.starts_with(key) && pair[key.len()..].starts_with('='))
        .map(|pair| &pair[key.len() + 1..])
}

fn parse_limit(query: &str) -> usize {
    get_param(query, "limit")
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(10_000)
        .min(10_000_000)
}

fn parse_no_list(query: &str) -> bool {
    matches!(get_param(query, "no_list"), Some("true") | Some("1"))
}

// ── Handlers ─────────────────────────────────────────────────────────────────
fn sieve_handler(query: &str) -> Response {
    let limit   = parse_limit(query);
    let no_list = parse_no_list(query);

    let start      = Instant::now();
    let primes     = sieve_of_eratosthenes(limit);
    let elapsed_us = start.elapsed().as_micros();

    eprintln!("sieve limit={limit} count={} elapsed_us={elapsed_us}", primes.len());

    let body = if no_list {
        serde_json::json!({
            "runtime":    "wasm-rust",
            "limit":      limit,
            "count":      primes.len(),
            "elapsed_us": elapsed_us,
        })
        .to_string()
    } else {
        serde_json::json!({
            "runtime":    "wasm-rust",
            "limit":      limit,
            "count":      primes.len(),
            "primes":     primes,
            "elapsed_us": elapsed_us,
        })
        .to_string()
    };

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
// #[http_component] is invoked once per HTTP request by Spin's Wasmtime host.
// No server loop — Spin's HTTP trigger handles accept()/dispatch.
// max_instances = 1 in spin.toml caps concurrency to match WASI P1 single-thread constraint.
#[http_component]
fn handle(req: IncomingRequest) -> Response {
    let path_with_query = req.path_with_query().unwrap_or_default();
    let (path, query) = match path_with_query.find('?') {
        Some(i) => (&path_with_query[..i], &path_with_query[i + 1..]),
        None    => (path_with_query.as_str(), ""),
    };

    match path {
        "/sieve"  => sieve_handler(query),
        "/health" => health_handler(),
        _         => Response::builder().status(404).body("not found").build(),
    }
}
