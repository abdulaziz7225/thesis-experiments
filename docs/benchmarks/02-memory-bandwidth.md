# Benchmark 02 — Memory Bandwidth

## Task description

Each variant exposes an HTTP service that **allocates a byte buffer of configurable size, fills it with a deterministic pattern, and computes a SHA-256 hash** over the entire buffer. No filesystem or network I/O is involved; the name "I/O bound" refers to the workload being bounded by memory bandwidth rather than CPU arithmetic.

## Workload

`GET /membw?size_kb=N&no_hash=0|1`

1. Allocate a heap buffer of `N × 1024` bytes.
2. Fill every byte with `index & 0xFF` (deterministic, repeating 0–255 pattern).
3. Compute SHA-256 over the full buffer using the platform's native crypto library.
4. Return the hex-encoded digest. `elapsed_us` captures only the alloc + fill + hash time (excludes HTTP framing).

**Parameters:**

| Parameter | Default | Max    | Description                                                          |
| --------- | ------- | ------ | -------------------------------------------------------------------- |
| `size_kb` | 64      | 10 240 | Buffer size in kilobytes                                             |
| `no_hash` | `0`     | —      | When `1`, skips SHA-256 (measures raw allocation and fill cost only) |

**Response:**

```json
{
  "runtime": "rust-docker",
  "size_kb": 64,
  "sha256": "4a8a08f09d37b73795649038408b5f33...",
  "elapsed_us": 312
}
```

`GET /health` returns HTTP 200 and is used for liveness/readiness probes.

The benchmark harness reports two artifact-size metrics for this workload: `binary_sizes.json` (the raw `.wasm` for Spin variants or the stripped scratch binary for Docker variants) and `image_sizes.json` (the full OCI image as pushed). See [notes-on-metrics.md](../reference/notes-on-metrics.md) for the distinction.

## Benchmark rationale

The memory-bandwidth workload complements the prime sieve by stressing a different axis:

- **Heap allocation pressure** — buffer size is tunable, enabling allocation-scaling experiments
- **Memory bandwidth** — the fill and hash passes both stream sequentially over a contiguous buffer
- **Crypto throughput** — SHA-256 over a large buffer reflects a realistic server-side hashing task (e.g. content checksumming)
- **`no_hash=1` mode** — isolates pure allocation + fill cost from the hashing cost, allowing the two components to be measured independently

Together with the prime sieve, this gives a two-point picture: CPU-arithmetic performance (sieve) vs memory-bandwidth performance (memory-bandwidth).

## Variants

| Variant         | Runtime             | Language         | NodePort |
| --------------- | ------------------- | ---------------- | -------- |
| `wasm-rust`     | Wasmtime (SpinKube) | Rust (WASI P2)   | 30081    |
| `wasm-tinygo`   | Wasmtime (SpinKube) | TinyGo (WASI P1) | 30082    |
| `docker-rust`   | runc                | Rust (Axum)      | 30083    |
| `docker-golang` | runc                | Go (net/http)    | 30084    |

The same NodePorts are reused across examples. Only one experiment namespace may be active at a time — `run_experiment.sh` tears down the previous namespace before deploying.

## Concurrency constraints (limited mode)

Identical to the prime sieve experiment:

- `docker-rust`: `TOKIO_WORKER_THREADS=1`
- `docker-golang`: `GOMAXPROCS=1`
- Wasm variants: inherently single-threaded (one Spin component instance)

The unlimited mode uses `TOKIO_WORKER_THREADS=4`, `GOMAXPROCS=4`, and `replicas=4` for the SpinApp variants — matching the four physical vCPUs of the Hetzner ccx23 host. The K8s `limits.cpu` is raised to `4000m` in the manifests so cgroup CPU bandwidth control does not throttle the added threads.
