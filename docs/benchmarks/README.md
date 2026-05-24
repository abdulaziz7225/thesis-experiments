# Benchmark experiments

Four complementary HTTP workloads, each exercising a different cost
dimension of the runtime + language combination. Same variant matrix across
all four; each variant is deployed to the same single-node Kubernetes
cluster on Hetzner and load-tested with k6.

| Example               | Workload class                | Hot path                                                                    | Spec                                             |
| --------------------- | ----------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------ |
| `01-prime-sieve`      | **CPU-bound**                 | Integer compute (Sieve of Eratosthenes)                                     | [01-prime-sieve.md](01-prime-sieve.md)           |
| `02-memory-bandwidth` | **memory-bound**              | Bulk heap allocation + SHA-256 over a configurable buffer                   | [02-memory-bandwidth.md](02-memory-bandwidth.md) |
| `03-http-fanout`      | **I/O-bound**                 | N concurrent outbound HTTP GETs to an in-cluster `io-echo` backend          | [03-http-fanout.md](03-http-fanout.md)           |
| `04-json-roundtrip`   | **serialization + allocator** | Parse a posted JSON integer array, sort, aggregate, re-serialise (sweeps N) | [04-json-roundtrip.md](04-json-roundtrip.md)     |

All four expose the same four variants on the same NodePorts:

| Variant         | Runtime             | Language         | NodePort |
| --------------- | ------------------- | ---------------- | -------- |
| `wasm-rust`     | Wasmtime (SpinKube) | Rust (WASI P2)   | 30081    |
| `wasm-tinygo`   | Wasmtime (SpinKube) | TinyGo (WASI P1) | 30082    |
| `docker-rust`   | runc                | Rust (Axum)      | 30083    |
| `docker-golang` | runc                | Go (net/http)    | 30084    |

## What each spec contains

Each `NN-*.md` file is a standalone reference card with the same five sections:

1. **Task description** — one paragraph: what the service does
2. **Workload** — endpoint signature, numbered algorithm steps, parameter table, JSON response example
3. **Benchmark rationale** — which axes the workload stresses and how it relates to the other three examples
4. **Variants** — the four-row variant matrix above (sometimes with an inter-section note about workload-specific infrastructure, e.g. the io-echo backend for 03)
5. **Concurrency constraints (limited mode)** — single-thread baseline values + the unlimited-mode shape

For the cross-cutting topics that don't belong in any one spec (what
`container_memory_rss` actually measures, why unlimited mode is not 3-4×
limited, etc.), see [../reference/notes-on-metrics.md](../reference/notes-on-metrics.md).

## How to actually run them

The orchestrator shell scripts live in `benchmarks/<example>/` at the repo
root; running them is covered in
[../operate/run-benchmarks.md](../operate/run-benchmarks.md). This folder
holds **what** each experiment measures; that folder holds **how** to
invoke it.
