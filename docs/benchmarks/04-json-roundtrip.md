# Benchmark 04 — JSON round-trip

## Task description

Each variant exposes an HTTP service that **accepts a POSTed JSON integer array, parses it, sorts it descending, computes aggregate statistics (count, sum, min, max, mean, median, stdev), and returns the aggregates as JSON** (optionally including the sorted array). The workload exercises the serialisation + allocator hot path of a typical microservice request handler.

## Workload

`POST /jsontx?n=N&no_list=0|1` with `Content-Type: application/json`, body = JSON array of N integers.

1. Read the request body off the WASI HTTP boundary (host → guest copy for Spin variants; standard tokio / net/http buffering for Docker variants).
2. Parse the body as `Vec<i64>` / `[]int64` via the platform's standard JSON deserialiser (`serde_json` for Rust, `encoding/json` for Go and TinyGo).
3. Sort the parsed array descending; compute count / sum / min / max / mean / median / stdev. Median is defined identically across all four variants as `arr[(n-1)/2]` after the descending sort (mid-low for even N).
4. Re-serialise the aggregates (and optionally the sorted array) as JSON.
5. Return the response. `elapsed_us` captures parse-through-reserialise (excludes inbound HTTP framing).

**Parameters:**

| Parameter | Default                 | Max     | Description                                                                                                        |
| --------- | ----------------------- | ------- | ------------------------------------------------------------------------------------------------------------------ |
| `n`       | 1 000                   | 100 000 | Array length per request — also the sweep dimension (see below)                                                    |
| `no_list` | `1` (load-test default) | —       | When `1`, omits the `sorted` array from the response (eliminates a serialisation confound during throughput tests) |

The actual array length is sourced from the parsed body on the server; the query-string `n` is informational and used by the k6 harness for sweep tagging only.

**Response:**

```json
{
  "runtime":    "rust-docker",
  "n":          1000,
  "count":      1000,
  "sum":        2147439112,
  "min":        2654732,
  "max":        4292838817,
  "mean":       2147439.112,
  "median":     2147483648,
  "stdev":      1238452.7,
  "elapsed_us": 412,
  "sorted":     [4292838817, 4290184056, ...]
}
```

`GET /health` returns HTTP 200 and is used for liveness/readiness probes.

The benchmark harness reports two artifact-size metrics for this workload: `binary_sizes.json` (the raw `.wasm` for Spin variants or the stripped scratch binary for Docker variants) and `image_sizes.json` (the full OCI image as pushed). See [notes-on-metrics.md](../reference/notes-on-metrics.md) for the distinction.

## Benchmark rationale

The JSON round-trip workload complements the previous three experiments by stressing a fourth, distinct axis:

- **Serialisation hot path** — exercises `serde_json` (Rust) and `encoding/json` (Go / TinyGo) under realistic microservice payload shapes
- **Allocator churn on small irregular objects** — JSON deserialisation produces many small allocations, stressing the heap allocator differently from 02's bulk contiguous buffer
- **Host ↔ guest HTTP-body copy** — for Spin variants, the request body crosses the WASI HTTP boundary on every request; at large N this is a Wasm-specific cost that 01–03 do not exercise (01 and 02 generate their working set inside the guest; 03's outbound bodies are small and few)
- **`no_list=1` mode** — isolates parse + transform from the re-serialise cost

Together with 01 (CPU-bound), 02 (memory-bound), and 03 (I/O-bound), this gives a four-point picture covering the dominant cost dimensions of a microservice request path.

## Variants

| Variant         | Runtime             | Language         | NodePort |
| --------------- | ------------------- | ---------------- | -------- |
| `wasm-rust`     | Wasmtime (SpinKube) | Rust (WASI P2)   | 30081    |
| `wasm-tinygo`   | Wasmtime (SpinKube) | TinyGo (WASI P1) | 30082    |
| `docker-rust`   | runc                | Rust (Axum)      | 30083    |
| `docker-golang` | runc                | Go (net/http)    | 30084    |

Unlike 01–03, the 04 load harness runs an **N-sweep** at the request-body level: one k6 invocation per `N ∈ {100, 1000, 10 000, 100 000}` per variant, producing four per-variant `<variant>_n<N>_summary.json` files plus a dedicated `n_sweep.png` line chart (throughput-vs-N, log-x). The middle of the sweep (`N = 10 000`) is aliased as the "default" k6 summary so the standard throughput / latency / error-rate panels render against a representative payload size. The same NodePorts are reused across all four examples — only one experiment namespace may be active at a time.

## Concurrency constraints (limited mode)

Identical to the prime sieve experiment:

- `docker-rust`: `TOKIO_WORKER_THREADS=1`
- `docker-golang`: `GOMAXPROCS=1`
- Wasm variants: inherently single-threaded (one Spin component instance)

The unlimited mode uses `TOKIO_WORKER_THREADS=4`, `GOMAXPROCS=4`, and `replicas=4` for the SpinApp variants — matching the four physical vCPUs of the Hetzner ccx23 host. The K8s `limits.cpu` is raised to `4000m` in the manifests so cgroup CPU bandwidth control does not throttle the added threads.
