# Benchmark 01 — Prime Sieve

## Task description

Each variant exposes an HTTP service that computes all prime numbers up to a configurable upper bound using the **Sieve of Eratosthenes** algorithm, then returns the result as JSON.

## Workload

`GET /sieve?limit=N&no_list=0|1`

1. Allocate a boolean array of size `N + 1`.
2. Run the classic sieve: for each prime `p` found, mark all multiples of `p` starting at `p²` as composite.
3. Collect all indices still marked prime into a result list.
4. Return the response. `elapsed_us` captures only the sieve computation time (excludes HTTP framing and JSON serialisation).

**Parameters:**

| Parameter | Default | Max        | Description                                                                                             |
| --------- | ------- | ---------- | ------------------------------------------------------------------------------------------------------- |
| `limit`   | 10 000  | 10 000 000 | Upper bound (inclusive)                                                                                 |
| `no_list` | `0`     | —          | When `1`, omits the `primes` array from the response to reduce serialisation overhead during load tests |

**Response:**

```json
{
  "runtime":    "rust-docker",
  "limit":      100000,
  "count":      9592,
  "primes":     [2, 3, 5, ...],
  "elapsed_us": 1823
}
```

`GET /health` returns HTTP 200 and is used for liveness/readiness probes.

The benchmark harness reports two artifact-size metrics for this workload: `binary_sizes.json` (the raw `.wasm` for Spin variants or the stripped scratch binary for Docker variants) and `image_sizes.json` (the full OCI image as pushed). See [notes-on-metrics.md](../reference/notes-on-metrics.md) for the distinction.

## Benchmark rationale

The sieve is a **CPU-bound, memory-sequential** workload. It exercises:

- **Heap allocation** — one boolean array proportional to `limit`
- **Sequential memory access** — the inner mark loop strides linearly through the array, which is cache-friendly
- **Single-threaded CPU throughput** — all variants are constrained to one thread/worker to eliminate parallelism as a variable

This makes it a clean signal for comparing raw compute overhead between the Docker (runc) and Wasm (Wasmtime/SpinKube) runtimes, independent of I/O or concurrency effects.

## Variants

| Variant         | Runtime             | Language         | NodePort |
| --------------- | ------------------- | ---------------- | -------- |
| `wasm-rust`     | Wasmtime (SpinKube) | Rust (WASI P2)   | 30081    |
| `wasm-tinygo`   | Wasmtime (SpinKube) | TinyGo (WASI P1) | 30082    |
| `docker-rust`   | runc                | Rust (Axum)      | 30083    |
| `docker-golang` | runc                | Go (net/http)    | 30084    |
