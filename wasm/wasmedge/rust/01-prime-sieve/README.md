# prime-sieve — Wasm (WasmEdge) + Rust

## Ecosystem Limitation: No Async HTTP for wasm32-wasip1

All other variants in this experiment use a mature async HTTP framework:

| Variant | HTTP Framework |
|---|---|
| `docker/rust` | axum (async, tokio) |
| `docker/golang` | net/http (stdlib, goroutine-per-request) |
| `wasm/tinygo` | raw TCP via //go:wasmimport (sync, single-threaded) |
| **`wasm/rust`** | **wasmedge_wasi_socket (sync, single-threaded)** |

### Why no async HTTP for wasm/rust?

The Rust async ecosystem is built on top of OS primitives (epoll, kqueue, io_uring) that
WASI P1 does not expose. This creates a fundamental gap:

- **tokio** — requires OS-level async I/O; does not compile to `wasm32-wasip1`.
- **hyper_wasi / tokio_wasi** — WasmEdge-maintained forks of hyper 0.14 / tokio 1.x that
  replace OS networking with WasmEdge's proprietary WASI socket extension. These crates
  are unmaintained as of 2025 and can no longer be reliably resolved from crates.io.
- **axum, warp, actix-web** — all depend on tokio; same limitation applies.
- **WASI P2 (wasi:http)** — defines a proper async HTTP interface via the Component
  Model, but WasmEdge's support is still experimental, and the Rust toolchain for P2
  components (`wasm32-wasip2` + `cargo-component`) is not yet stable enough for production
  benchmarking as of this writing.

### What this implementation uses

This service falls back to `std::net::TcpListener`, which WasmEdge exposes through its
WASI socket extension (`sock_accept`, `sock_listen`, etc.). The server accepts one
connection at a time (synchronous, single-threaded).

### Thesis implications

This is a documented **ecosystem maturity gap** for WebAssembly as a microservice runtime:

- Rust, the language most associated with WASM, cannot yet use its own production-grade
  async HTTP stack when targeting `wasm32-wasip1`.
- The missing async I/O layer limits throughput under concurrent load — the sync server
  serialises requests that an async server would handle in parallel.
- This is a fair finding for the thesis: the WASM runtime constraint itself introduces
  an architectural ceiling that Docker-based deployments do not face.

The core benchmark logic (sieve algorithm, query parameters, response schema) is identical
across all four variants. Only the HTTP transport layer differs here, and that difference
is a direct consequence of WASM ecosystem immaturity — not a deliberate design choice.
