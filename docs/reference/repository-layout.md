# Repository layout

```text
thesis-experiments/
├── backend/
│   └── io-echo/                          # Tiny Go HTTP backend with configurable delay (used by 03-http-fanout)
├── docker/
│   ├── rust/
│   │   ├── 01-prime-sieve/               # Docker + Rust (axum): Sieve of Eratosthenes              – CPU-bound
│   │   ├── 02-memory-bandwidth/          # Docker + Rust (axum): in-memory I/O + SHA-256            – memory-bound
│   │   ├── 03-http-fanout/               # Docker + Rust (axum + reqwest): outbound HTTP fan-out    – I/O-bound
│   │   └── 04-json-roundtrip/            # Docker + Rust (axum + serde): JSON parse / transform     – serialization
│   └── golang/
│       ├── 01-prime-sieve/               # Docker + Go (net/http): Sieve of Eratosthenes            – CPU-bound
│       ├── 02-memory-bandwidth/          # Docker + Go (net/http): in-memory I/O + SHA-256          – memory-bound
│       ├── 03-http-fanout/               # Docker + Go (net/http + goroutines): outbound HTTP fan-out – I/O-bound
│       └── 04-json-roundtrip/            # Docker + Go (net/http + encoding/json): JSON parse/tx    – serialization
├── wasm/
│   ├── rust/
│   │   ├── 01-prime-sieve/               # Spin/Rust (WASI P2): Sieve                               – CPU-bound
│   │   ├── 02-memory-bandwidth/          # Spin/Rust (WASI P2): I/O + SHA-256                       – memory-bound
│   │   ├── 03-http-fanout/               # Spin/Rust (WASI P2): outbound HTTP fan-out               – I/O-bound
│   │   └── 04-json-roundtrip/            # Spin/Rust (WASI P2): JSON parse / transform              – serialization
│   └── tinygo/
│       ├── 01-prime-sieve/               # Spin/TinyGo (WASI P1): Sieve                             – CPU-bound
│       ├── 02-memory-bandwidth/          # Spin/TinyGo (WASI P1): I/O + SHA-256                     – memory-bound
│       ├── 03-http-fanout/               # Spin/TinyGo (WASI P1): outbound HTTP fan-out             – I/O-bound
│       └── 04-json-roundtrip/            # Spin/TinyGo (WASI P1): JSON parse / transform            – serialization
├── k8s/
│   ├── 01-prime-sieve/                   # K8s manifests (namespace: prime-sieve)                   – CPU-bound
│   ├── 02-memory-bandwidth/              # K8s manifests (namespace: memory-bandwidth)              – memory-bound
│   ├── 03-http-fanout/                   # K8s manifests (namespace: http-fanout, + io-echo backend) – I/O-bound
│   └── 04-json-roundtrip/                # K8s manifests (namespace: json-roundtrip)                – serialization
├── benchmarks/
│   ├── shared/utils.py                   # Shared helpers (VARIANTS, VARIANT_LABELS, Prometheus, kubectl)
│   ├── shared/binary_sizes.py            # Extracts raw .wasm / binary sizes per variant
│   ├── 01-prime-sieve/                   # k6 load tests + analysis for prime-sieve (CPU-bound)
│   ├── 02-memory-bandwidth/              # k6 load tests + analysis for memory-bandwidth
│   ├── 03-http-fanout/                   # k6 load tests + analysis for http-fanout (I/O-bound)
│   └── 04-json-roundtrip/                # k6 N-sweep load tests + analysis for json-roundtrip
├── docs/                                 # This documentation tree
└── results/                              # Output directory (git-ignored)
    ├── 01-prime-sieve/
    ├── 02-memory-bandwidth/
    ├── 03-http-fanout/
    └── 04-json-roundtrip/
```

## Benchmark scripts per example

Every `benchmarks/<example>/` directory has the same five files:

| File                    | Purpose                                                                           |
| ----------------------- | --------------------------------------------------------------------------------- |
| `k6-load-test.js`       | k6 load-test script — configurable VUs and duration, emits a custom server metric |
| `cold_start.py`         | Cold (run 1) and warm (runs 2+) start measurement by scaling deployments 0 → 1    |
| `prometheus_metrics.py` | Queries Prometheus for memory and CPU per variant over a load-test window         |
| `analyze.py`            | Reads result files and generates chart PNGs (`--mode limited\|unlimited`)         |
| `run_experiment.sh`     | Orchestrator — health checks, load tests, cold start, sizes, charts               |

For what these scripts do end-to-end, see
[../operate/run-benchmarks.md](../operate/run-benchmarks.md).
