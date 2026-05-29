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

This repo depends on a sibling repo
[`thesis-infra-setup`](https://github.com/abdulaziz7225/thesis-infra-setup)
for the cluster provisioning side. Clone both repos as siblings under a
common parent directory:

```bash
mkdir -p ~/master-thesis && cd ~/master-thesis
git clone https://github.com/abdulaziz7225/thesis-experiments.git
git clone https://github.com/abdulaziz7225/thesis-infra-setup.git
cd thesis-experiments
```

Then once-only setup of the workstation (Python, Docker, Spin CLI,
cargo-component, TinyGo + Go 1.23.12, k6) — see
[docs/setup/01-prerequisites.md](docs/setup/01-prerequisites.md).

```bash
# 1. Bring the Hetzner cluster up (~10 min) — uses the sibling thesis-infra-setup repo
cd ../thesis-infra-setup && make up && make configure && make label && make deploy && cd -
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
export THESIS_NODE_IP=$(cd ../thesis-infra-setup && terraform output -raw instance_public_ip)

# 2. Build and push all 16 variant images + the io-echo backend
#    (per-variant commands at docs/build/)
export DOCKER_USER=<YOUR_DOCKERHUB_USERNAME>
# ... see docs/build/docker-variants.md, docs/build/wasm-variants.md,
#     docs/build/io-echo-backend.md ...

# 3. Run the simplest experiment
./benchmarks/01-prime-sieve/run_experiment.sh

# 4. View results
ls results/01-prime-sieve/limited/charts/
```

The full per-experiment command set is in
[docs/operate/run-benchmarks.md](docs/operate/run-benchmarks.md).

## Documentation

| Topic                                                                   | Where to look                                                                        |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Local prerequisites (Python, Docker, Spin CLI, TinyGo + Go 1.23.12, k6) | [docs/setup/01-prerequisites.md](docs/setup/01-prerequisites.md)                     |
| Bringing up the Hetzner Kubernetes cluster                              | [docs/setup/02-infrastructure.md](docs/setup/02-infrastructure.md)                   |
| Building and pushing the Docker variant images                          | [docs/build/docker-variants.md](docs/build/docker-variants.md)                       |
| Building and pushing the Wasm variant images                            | [docs/build/wasm-variants.md](docs/build/wasm-variants.md)                           |
| Building the io-echo backend (used by 03)                               | [docs/build/io-echo-backend.md](docs/build/io-echo-backend.md)                       |
| Deploying an experiment manually                                        | [docs/operate/deploy.md](docs/operate/deploy.md)                                     |
| Running the four benchmark experiments                                  | [docs/operate/run-benchmarks.md](docs/operate/run-benchmarks.md)                     |
| Limited vs unlimited mode                                               | [docs/operate/scaling-modes.md](docs/operate/scaling-modes.md)                       |
| Why only one example can be active at a time                            | [docs/operate/sequential-example-model.md](docs/operate/sequential-example-model.md) |
| Output layout and chart regeneration                                    | [docs/operate/output-structure.md](docs/operate/output-structure.md)                 |
| Removing experiments or destroying the VM                               | [docs/operate/teardown.md](docs/operate/teardown.md)                                 |
| What each experiment measures (4 reference cards)                       | [docs/benchmarks/](docs/benchmarks/)                                                 |
| What `container_memory_rss` measures, and why unlimited != 4× limited   | [docs/reference/notes-on-metrics.md](docs/reference/notes-on-metrics.md)             |
| Why SpinKube was chosen over WasmEdge / wasmCloud / Krustlet            | [docs/reference/runtime-choice.md](docs/reference/runtime-choice.md)                 |
| Repository tree and benchmark-script roster                             | [docs/reference/repository-layout.md](docs/reference/repository-layout.md)           |
| Pinned toolchain versions                                               | [docs/reference/toolchain-versions.md](docs/reference/toolchain-versions.md)         |

A complete docs landing page with one-line descriptions per file:
[docs/README.md](docs/README.md).
