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

## How to actually run them

The orchestrator shell scripts live in `benchmarks/<example>/` at the repo
root; running them is covered in
[../operate/run-benchmarks.md](../operate/run-benchmarks.md). This folder
holds **what** each experiment measures; that folder holds **how** to
invoke it.
