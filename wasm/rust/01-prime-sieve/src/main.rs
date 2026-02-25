// Rust + WASM (WasmEdge) – prime-sieve HTTP service
//
// NOTE: No mature async HTTP framework compiles reliably to wasm32-wasip1.
// hyper_wasi / tokio_wasi (WasmEdge-specific forks) are unmaintained.
// This service therefore uses std::net::TcpListener (sync, single-threaded)
// via WasmEdge's WASI socket extension. See README.md for full rationale.
//
// Build target: wasm32-wasip1  (see .cargo/config.toml)

use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::time::Instant;

// ── Algorithm ───────────────────────────────────────────────────────────────
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

// ── Query helpers ────────────────────────────────────────────────────────────
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

// ── HTTP ─────────────────────────────────────────────────────────────────────
fn respond(stream: &mut TcpStream, status: u16, content_type: &str, body: &str) {
    let status_text = if status == 200 { "OK" } else { "Not Found" };
    let _ = write!(
        stream,
        "HTTP/1.1 {status} {status_text}\r\n\
         Content-Type: {content_type}\r\n\
         Content-Length: {}\r\n\
         Connection: close\r\n\
         \r\n\
         {body}",
        body.len()
    );
}

fn handle_connection(stream: TcpStream) {
    let mut reader = BufReader::new(stream);

    // Read request line
    let mut request_line = String::new();
    if reader.read_line(&mut request_line).is_err() {
        return;
    }

    // Drain remaining headers
    loop {
        let mut h = String::new();
        match reader.read_line(&mut h) {
            Ok(n) if n <= 2 => break,
            Ok(_) => continue,
            Err(_) => return,
        }
    }

    // Recover the TcpStream from the BufReader to write the response
    let mut stream = reader.into_inner();

    // Parse "METHOD /path?query HTTP/1.1"
    let path_query = request_line
        .split_ascii_whitespace()
        .nth(1)
        .unwrap_or("/");
    let (path, query) = path_query.split_once('?').unwrap_or((path_query, ""));

    match path {
        "/sieve" => {
            let limit   = parse_limit(query);
            let no_list = parse_no_list(query);

            let start      = Instant::now();
            let primes     = sieve_of_eratosthenes(limit);
            let elapsed_us = start.elapsed().as_micros();

            eprintln!("sieve limit={limit} count={} elapsed_us={elapsed_us}", primes.len());

            let body = if no_list {
                serde_json::json!({
                    "runtime":    "rust-wasm",
                    "limit":      limit,
                    "count":      primes.len(),
                    "elapsed_us": elapsed_us,
                })
                .to_string()
            } else {
                serde_json::json!({
                    "runtime":    "rust-wasm",
                    "limit":      limit,
                    "count":      primes.len(),
                    "primes":     primes,
                    "elapsed_us": elapsed_us,
                })
                .to_string()
            };

            respond(&mut stream, 200, "application/json", &body);
        }

        "/health" => {
            respond(&mut stream, 200, "text/plain", "");
        }

        _ => {
            respond(&mut stream, 404, "text/plain", "not found");
        }
    }
}

// ── Entry point ──────────────────────────────────────────────────────────────
fn main() {
    let addr = "0.0.0.0:8080";
    let listener = TcpListener::bind(addr).expect("failed to bind");
    eprintln!("rust-wasm prime-sieve listening on {addr}");

    for stream in listener.incoming() {
        match stream {
            Ok(s) => handle_connection(s),
            Err(e) => eprintln!("accept error: {e}"),
        }
    }
}
