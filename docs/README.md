# Documentation

Reader-facing documentation for the thesis-experiments artefact bundle.
Top-level [README](../README.md) is the lean entry point with a Quickstart;
this tree holds the full detail.

Read these in the order you need them — there is no required reading
sequence beyond `setup/01-prerequisites.md → setup/02-infrastructure.md`.

## setup/ — get the environment ready

| File                                                     | What's in it                                                                            |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| [setup/01-prerequisites.md](setup/01-prerequisites.md)   | Local tools: Python venv, Docker, Spin CLI, cargo-component, TinyGo + Go 1.23.12 SDK    |
| [setup/02-infrastructure.md](setup/02-infrastructure.md) | Provisioning the Hetzner Kubernetes node, deploying SpinOperator + Prometheus + Grafana |

## build/ — compile and push the variant images

| File                                                 | What's in it                                                                                                                                                 |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [build/docker-variants.md](build/docker-variants.md) | `docker build` + `docker push` for the four Rust- and Go-on-runc variants                                                                                    |
| [build/wasm-variants.md](build/wasm-variants.md)     | `cargo component build` and `tinygo build`, then `spin registry push` for the four Wasm variants; documents the Go 1.23.12 PATH override required for TinyGo |
| [build/io-echo-backend.md](build/io-echo-backend.md) | Building the small Go HTTP delay backend that the 03 (I/O-bound) experiment fans out to                                                                      |

## operate/ — deploy and run experiments

| File                                                                       | What's in it                                                                              |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| [operate/deploy.md](operate/deploy.md)                                     | `kubectl apply` per experiment + the four-port smoke-test                                 |
| [operate/run-benchmarks.md](operate/run-benchmarks.md)                     | Running each `run_experiment.sh` orchestrator; per-experiment knobs                       |
| [operate/scaling-modes.md](operate/scaling-modes.md)                       | What `--scaling-experiment limited\|unlimited\|both` actually does                        |
| [operate/sequential-example-model.md](operate/sequential-example-model.md) | Why only one example can be active at a time and how the orchestrators enforce it         |
| [operate/output-structure.md](operate/output-structure.md)                 | The `results/<example>/` directory layout and how to regenerate charts without re-running |
| [operate/observability.md](operate/observability.md)                       | Grafana + Prometheus URLs, useful PromQL queries                                          |
| [operate/teardown.md](operate/teardown.md)                                 | Removing experiment workloads and destroying the VM                                       |

## reference/ — look up details

| File                                                               | What's in it                                                                                                                                                                                    |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [reference/repository-layout.md](reference/repository-layout.md)   | The annotated source tree and per-example benchmark-script roster                                                                                                                               |
| [reference/toolchain-versions.md](reference/toolchain-versions.md) | The pinned versions of every component (Kubernetes, SpinOperator, Spin CLI, Rust, Go, TinyGo, k6, …)                                                                                            |
| [reference/runtime-choice.md](reference/runtime-choice.md)         | Why **SpinKube (Wasmtime/Cranelift)** was picked over WasmEdge, wasmCloud, Krustlet, and friends                                                                                                |
| [reference/notes-on-metrics.md](reference/notes-on-metrics.md)     | What `container_memory_rss` actually measures, the concurrency model per variant in limited vs unlimited mode, and why unlimited is not 3-4× limited; `binary_sizes.json` vs `image_sizes.json` |
| [reference/troubleshooting.md](reference/troubleshooting.md)       | Cluster-collapse recovery, common image-pull failures, kube-proxy / conntrack saturation symptoms                                                                                               |

## benchmarks/ — one spec per experiment

| File                                                                   | Workload class            |
| ---------------------------------------------------------------------- | ------------------------- |
| [benchmarks/01-prime-sieve.md](benchmarks/01-prime-sieve.md)           | CPU-bound                 |
| [benchmarks/02-memory-bandwidth.md](benchmarks/02-memory-bandwidth.md) | memory-bound              |
| [benchmarks/03-http-fanout.md](benchmarks/03-http-fanout.md)           | I/O-bound                 |
| [benchmarks/04-json-roundtrip.md](benchmarks/04-json-roundtrip.md)     | serialization + allocator |

Each file is a short reference spec — task description, workload contract,
parameters, response shape, rationale, variant matrix, concurrency
constraints. See also [benchmarks/README.md](benchmarks/README.md) for a
side-by-side comparison.
