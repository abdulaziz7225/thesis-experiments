# Master Thesis Experiments

A 2×2 benchmark matrix comparing **Docker (runc)** vs **WebAssembly
(SpinKube / Wasmtime)** as the runtime for **Rust** and **Go-family**
microservices on a single-node Kubernetes cluster. The same HTTP
workload is implemented four times across four complementary examples;
benchmarks measure startup latency, throughput, latency distribution,
memory and CPU footprint, OCI image size, and binary artifact size.

## What this is

Four complementary HTTP workloads, each exercising a different cost
dimension of the runtime + language combination:

| Example               | Workload class                | Hot path                                                           |
| --------------------- | ----------------------------- | ------------------------------------------------------------------ |
| `01-prime-sieve`      | **CPU-bound**                 | Integer compute (Sieve of Eratosthenes)                            |
| `02-memory-bandwidth` | **memory-bound**              | Bulk heap allocation + SHA-256 over a configurable buffer          |
| `03-http-fanout`      | **I/O-bound**                 | N concurrent outbound HTTP GETs to an in-cluster `io-echo` backend |
| `04-json-roundtrip`   | **serialization + allocator** | Parse a posted JSON integer array, sort, aggregate, re-serialise   |

## Variant matrix

| Variant         | Runtime                                 | Language           | NodePort |
| --------------- | --------------------------------------- | ------------------ | -------- |
| `wasm-rust`     | SpinKube / Wasmtime-Cranelift (WASI P2) | Rust 1.94          | 30081    |
| `wasm-tinygo`   | SpinKube / Wasmtime-Cranelift (WASI P1) | TinyGo 0.40.1      | 30082    |
| `docker-rust`   | runc (OCI)                              | Rust 1.94 (Axum)   | 30083    |
| `docker-golang` | runc (OCI)                              | Go 1.26 (net/http) | 30084    |

## Quickstart

Cluster provisioning lives in the sibling repo
[`thesis-infra-setup`](https://github.com/abdulaziz7225/thesis-infra-setup);
clone both as siblings under a common parent:

```bash
mkdir -p ~/master-thesis && cd ~/master-thesis
git clone https://github.com/abdulaziz7225/thesis-experiments.git
git clone https://github.com/abdulaziz7225/thesis-infra-setup.git
cd thesis-experiments
```

First, set up the workstation tools (Python, Docker, Spin CLI,
cargo-component, TinyGo + Go 1.23.12, k6) —
see [docs/setup/01-prerequisites.md](docs/setup/01-prerequisites.md). Then:

```bash
# 1. Bring the Hetzner cluster up (~10 min)
cd ../thesis-infra-setup && make up && make configure && make label && make deploy && cd -
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
export THESIS_NODE_IP=$(cd ../thesis-infra-setup && terraform output -raw instance_public_ip)

# 2. Build and push the variant images + io-echo backend (see docs/build/)
export DOCKER_USER=<YOUR_DOCKERHUB_USERNAME>

# 3. Run an experiment and view its charts
./benchmarks/01-prime-sieve/run_experiment.sh
ls results/01-prime-sieve/limited/charts/
```

The full per-experiment command set is in
[docs/operate/run-benchmarks.md](docs/operate/run-benchmarks.md).

## Documentation

### setup/ — get the environment ready

| File                                                               | What's in it                                                                            |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| [docs/setup/01-prerequisites.md](docs/setup/01-prerequisites.md)   | Local tools: Python venv, Docker, Spin CLI, cargo-component, TinyGo + Go 1.23.12 SDK    |
| [docs/setup/02-infrastructure.md](docs/setup/02-infrastructure.md) | Provisioning the Hetzner Kubernetes node, deploying SpinOperator + Prometheus + Grafana |

### build/ — compile and push the variant images

| File                                                           | What's in it                                                                                                                                                 |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [docs/build/docker-variants.md](docs/build/docker-variants.md) | `docker build` + `docker push` for the four Rust- and Go-on-runc variants                                                                                    |
| [docs/build/wasm-variants.md](docs/build/wasm-variants.md)     | `cargo component build` and `tinygo build`, then `spin registry push` for the four Wasm variants; documents the Go 1.23.12 PATH override required for TinyGo |
| [docs/build/io-echo-backend.md](docs/build/io-echo-backend.md) | Building the small Go HTTP delay backend that the 03 (I/O-bound) experiment fans out to                                                                      |

### operate/ — deploy and run experiments

| File                                                                                 | What's in it                                                                              |
| ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| [docs/operate/deploy.md](docs/operate/deploy.md)                                     | `kubectl apply` per experiment + the four-port smoke-test                                 |
| [docs/operate/run-benchmarks.md](docs/operate/run-benchmarks.md)                     | Running each `run_experiment.sh` orchestrator; per-experiment knobs                       |
| [docs/operate/scaling-modes.md](docs/operate/scaling-modes.md)                       | What `--scaling-experiment limited\|unlimited\|both` actually does                        |
| [docs/operate/sequential-example-model.md](docs/operate/sequential-example-model.md) | Why only one example can be active at a time and how the orchestrators enforce it         |
| [docs/operate/output-structure.md](docs/operate/output-structure.md)                 | The `results/<example>/` directory layout and how to regenerate charts without re-running |
| [docs/operate/teardown.md](docs/operate/teardown.md)                                 | Removing experiment workloads and destroying the VM                                       |

### reference/ — look up details

| File                                                                         | What's in it                                                                                                                                                                                    |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [docs/reference/repository-layout.md](docs/reference/repository-layout.md)   | The annotated source tree and per-example benchmark-script roster                                                                                                                               |
| [docs/reference/toolchain-versions.md](docs/reference/toolchain-versions.md) | The pinned versions of every component (Kubernetes, SpinOperator, Spin CLI, Rust, Go, TinyGo, k6, …)                                                                                            |
| [docs/reference/runtime-choice.md](docs/reference/runtime-choice.md)         | Why **SpinKube (Wasmtime/Cranelift)** was picked over WasmEdge, wasmCloud, Krustlet, and friends                                                                                                |
| [docs/reference/notes-on-metrics.md](docs/reference/notes-on-metrics.md)     | What `container_memory_rss` actually measures, the concurrency model per variant in limited vs unlimited mode, and why unlimited is not 3-4× limited; `binary_sizes.json` vs `image_sizes.json` |

### benchmarks/ — one spec per experiment

| File                                                                             | Workload class            |
| -------------------------------------------------------------------------------- | ------------------------- |
| [docs/benchmarks/01-prime-sieve.md](docs/benchmarks/01-prime-sieve.md)           | CPU-bound                 |
| [docs/benchmarks/02-memory-bandwidth.md](docs/benchmarks/02-memory-bandwidth.md) | memory-bound              |
| [docs/benchmarks/03-http-fanout.md](docs/benchmarks/03-http-fanout.md)           | I/O-bound                 |
| [docs/benchmarks/04-json-roundtrip.md](docs/benchmarks/04-json-roundtrip.md)     | serialization + allocator |
