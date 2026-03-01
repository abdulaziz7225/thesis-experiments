# prime-sieve — WASM (WasmEdge) + TinyGo

## Ecosystem Limitation: No Standard HTTP for wasip1

All other variants in this experiment use a higher-level HTTP abstraction:

| Variant           | HTTP Framework                                          |
| ----------------- | ------------------------------------------------------- |
| `docker/rust`     | axum (async, tokio)                                     |
| `docker/golang`   | net/http (stdlib, goroutine-per-request)                |
| `wasm/rust`       | wasmedge_wasi_socket (sync, single-threaded)            |
| **`wasm/tinygo`** | **raw TCP via //go:wasmimport (sync, single-threaded)** |

### Why not net/http?

TinyGo's `net/http` cannot serve HTTP in a WasmEdge 0.14.x environment:

**Problem 1 — TinyGo ≤0.27.0 + WasmEdge 0.14.x ABI mismatch**
TinyGo 0.27.0 implemented WASI socket support by calling WasmEdge's proprietary
`sock_open`/`sock_bind`/`sock_listen`/`sock_accept` extension functions from
`wasi_snapshot_preview1`. WasmEdge 0.14.x changed the ABI of these functions
(parameter semantics, struct layout). The result: `sock_open` fails at runtime
but TinyGo's `net` package propagates this as a `nil` error — causing
`http.ListenAndServe` to return immediately with `nil` and the process to exit
normally (exit code 0) instead of serving. This manifests as
`Completed → CrashLoopBackOff` in Kubernetes.

**Problem 2 — TinyGo 0.28+ Netdev architecture regression**
TinyGo 0.28 refactored `net/http` to require an explicit `machine.Netdev` driver.
For the `wasip1` target, no driver is auto-registered, so any call into `net/http`
fails with `"server error: Netdev not set"`.

### Why not WASI Preview 2?

WasmEdge 0.14.x does not implement the WASI P2 Component Model
(`wasi:http/proxy`, `wasi:sockets/tcp`). Its P2 support
is still incomplete as of early 2026. Switching to a P2-capable runtime
(Wasmtime) would eliminate TinyGo from the comparison entirely — see
`runtime-choice.md` for the full evaluation.

### What this implementation uses

The code is split into two files:

- **`main.go`** — standard `net/http` handler code, nearly identical to
  `docker/golang`. Uses `http.ResponseWriter`, `*http.Request`,
  `http.NewServeMux()`, `json.NewEncoder(w).Encode()`, `r.URL.Query()`.
  Calls `serveWasmEdge(addr, mux)` instead of `http.ListenAndServe`.

- **`server.go`** — infrastructure layer. Provides `serveWasmEdge()` using
  WasmEdge's WASI socket extension (`sock_open`/`bind`/`listen`/`accept` via
  `//go:wasmimport`). Uses `http.ReadRequest` (pure Go parser, no OS calls)
  to convert raw bytes into `*http.Request`, and a `wasResponseWriter` struct
  implementing `http.ResponseWriter` to buffer and send the response.
  Function signatures match `wasmedge_wasi_socket v0.5.5` (src/socket.rs).

The server accepts one connection at a time (synchronous, single-threaded):
no goroutine scheduler is involved in the accept loop.

### Thesis implications

This mirrors the finding documented for `wasm/rust`: **both** WASM variants
are forced into a single-threaded, sequential request-handling model by the
constraints of WasmEdge's WASI P1 socket extension. WASI P1 exposes no
`epoll`/`io_uring`/`kqueue` primitives, making async I/O impossible regardless
of the source language's native concurrency model.

- Docker/Rust uses tokio's full async runtime.
- Docker/Go uses goroutines with M:N OS-thread scheduling.
- Both WASM variants serialise requests through a single accept-handle-respond loop.

This architectural ceiling — not imposed by the language but by the WASM
runtime's system interface — is a primary thesis finding on the current maturity
of WASM as a microservice platform.

The core benchmark logic (sieve algorithm, query parameters, response schema)
is identical across all four variants. Only the transport layer differs, and
that difference is a direct consequence of ecosystem constraints.
