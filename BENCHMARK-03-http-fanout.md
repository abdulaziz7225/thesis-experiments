# Benchmark 03 — HTTP fan-out (I/O-bound)

## Task description

Each variant exposes an HTTP service that **fans a single inbound request out into N concurrent outbound HTTP GETs** against an in-cluster `io-echo` backend Deployment, awaits all N responses, and returns an aggregated JSON summary. The backend sleeps for `delay_ms` before responding, so each inbound request is dominated by **outbound I/O wait** rather than CPU work — the workload is I/O-bound by design.

## Workload

`GET /fanout?n=N&delay_ms=D&no_list=0|1`

1. Parse `n` and `delay_ms` from the query string (defaults and caps below).
2. Dispatch N outbound `GET http://io-echo.http-fanout.svc.cluster.local:80/echo?delay_ms=D&size_b=256` calls — `spin_sdk::http::send + futures::join_all` (Rust, concurrent), `reqwest::Client + futures::join_all` (Docker Rust, concurrent), `net/http + goroutines + sync.WaitGroup` (Docker Go, concurrent). The wasm-tinygo variant issues them **sequentially** via `spinhttp.Send`: TinyGo's wasip1 runtime panics on `sync.WaitGroup.Wait`, so the Rust + WASI P2 concurrent fan-out pattern cannot be replicated under WASI P1 + TinyGo today — itself a thesis-relevant observation.
3. Await all N responses; count successful (2xx) vs failed.
4. Return the response. `elapsed_us` captures only the fan-out wall-clock (first outbound dispatched → all outbounds complete; excludes inbound HTTP framing).

**Parameters:**

| Parameter | Default | Max | Description |
|-----------|---------|-----|-------------|
| `n` | 5 | 20 | Number of concurrent outbound HTTP GETs per inbound request |
| `delay_ms` | 50 | 1 000 | Per-outbound backend sleep, tunes the I/O-wait floor independently of fan-out width |
| `no_list` | `0` | — | When `1`, omits the per-outbound `responses` status array (eliminates a serialisation confound during throughput tests) |

**Response:**

```json
{
  "runtime":    "rust-docker",
  "n":          5,
  "delay_ms":   50,
  "ok_count":   5,
  "err_count":  0,
  "elapsed_us": 53124,
  "responses":  [200, 200, 200, 200, 200]
}
```

`GET /health` returns HTTP 200 and is used for liveness/readiness probes.

## Benchmark rationale

The HTTP fan-out workload complements the prime sieve and memory-bandwidth experiments by stressing a third axis:

- **I/O wait dominance** — per-request latency tracks `delay_ms`, not CPU; the rate-limiting factor is outbound HTTP scheduling, not arithmetic
- **Host-call overhead** — Spin's `wasi:http/outgoing-handler` boundary cost vs `reqwest` / `net/http` syscall cost
- **Concurrent I/O scheduling** — Rust async (`futures::join_all`) vs Go goroutines vs TinyGo's enforced sequential dispatch (a real WASI P1 + Spin Go SDK ceiling, not an implementation choice)
- **`no_list=1` mode** — isolates inbound-side serialisation from outbound-side wait

Together with the prime sieve (CPU-bound, 01) and memory-bandwidth (memory-bound, 02), this gives a three-point picture: CPU-arithmetic, memory bandwidth, and outbound I/O wait.

## Variants

| Variant | Runtime | Language | NodePort |
|---------|---------|----------|----------|
| `wasm-rust` | Wasmtime (SpinKube) | Rust (WASI P2) | 30081 |
| `wasm-tinygo` | Wasmtime (SpinKube) | TinyGo (WASI P1) | 30082 |
| `docker-rust` | runc | Rust (Axum) | 30083 |
| `docker-golang` | runc | Go (net/http) | 30084 |

A small Go `io-echo` backend Deployment lives in the same namespace as the four variants and is the outbound HTTP target. It is intentionally **not** part of the comparison matrix — holding the per-outbound delay and response size stable at the backend turns variation in measured throughput and latency into a runtime-and-language signal rather than backend noise. The two Spin variants set `allowed_outbound_hosts = ["http://io-echo.http-fanout.svc.cluster.local:80"]` in `spin.toml`, gating outbound HTTP to the backend only (deny-by-default posture). The same NodePorts are reused across all four examples — only one experiment namespace may be active at a time.

## Concurrency constraints (limited mode)

Identical to the prime sieve experiment:

- `docker-rust`: `TOKIO_WORKER_THREADS=1`
- `docker-golang`: `GOMAXPROCS=1`
- Wasm variants: inherently single-threaded (one Spin component instance)

The unlimited mode uses `TOKIO_WORKER_THREADS=4`, `GOMAXPROCS=4`, and `replicas=4` for the SpinApp variants — matching the four physical vCPUs of the Hetzner ccx23 host. The K8s `limits.cpu` is raised to `4000m` in the manifests so cgroup CPU bandwidth control does not throttle the added threads.
