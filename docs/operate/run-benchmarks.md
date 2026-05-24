# Running the benchmark experiments

Each experiment has one orchestrator script at
`benchmarks/<example>/run_experiment.sh` that handles namespace
teardown, redeployment, health checks, k6 load tests, Prometheus metric
collection, cold/warm-start measurement, image and binary size
collection, and chart generation. **You only run one script per
experiment.**

Before any of these, complete [../setup/](../setup/) and
[../build/](../build/), and export the two environment variables:

```bash
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
export THESIS_NODE_IP=$(cd ../thesis-infra-setup && terraform output -raw instance_public_ip)
source .venv/bin/activate    # the Python venv from prerequisites
```

For what each experiment _measures_, see
[../benchmarks/](../benchmarks/). This file is about _how_ to invoke
each one.

## 01-prime-sieve (CPU-bound)

```bash
# Default: limited threads, 50 VUs, 60 s
./benchmarks/01-prime-sieve/run_experiment.sh

# Scaling experiment (both limited and unlimited passes)
./benchmarks/01-prime-sieve/run_experiment.sh \
    --scaling-experiment both \
    --users 50 \
    --duration 60s \
    --cold-start-runs 6
```

Workload spec: [../benchmarks/01-prime-sieve.md](../benchmarks/01-prime-sieve.md).

## 02-memory-bandwidth (memory-bound)

```bash
# run_experiment.sh tears down sibling example namespaces first automatically
./benchmarks/02-memory-bandwidth/run_experiment.sh

# Scaling experiment (both limited and unlimited passes)
./benchmarks/02-memory-bandwidth/run_experiment.sh \
    --scaling-experiment both \
    --size-kb 64 \
    --users 50 \
    --duration 60s
```

Workload spec: [../benchmarks/02-memory-bandwidth.md](../benchmarks/02-memory-bandwidth.md).

## 03-http-fanout (I/O-bound)

The I/O-bound counterpart to 01 and 02. Each variant exposes
`GET /fanout?n=N&delay_ms=D` and dispatches N concurrent outbound HTTP
GETs to an in-cluster `io-echo` backend Deployment; per-request latency
is dominated by outbound I/O wait. Spin variants use
`spin_sdk::http::send + futures::join_all` (Rust) or sequential
`spinhttp.Send` (TinyGo, due to a WASI P1 sync.WaitGroup limitation);
Docker variants use `reqwest` (Rust, concurrent) and `net/http`
(Go, concurrent goroutines).

```bash
# run_experiment.sh tears down sibling examples and brings up io-echo
./benchmarks/03-http-fanout/run_experiment.sh

# Scaling experiment, full sweep:
./benchmarks/03-http-fanout/run_experiment.sh \
    --scaling-experiment both \
    --n 5 \
    --delay-ms 50 \
    --users 50 \
    --duration 60s
```

Workload spec: [../benchmarks/03-http-fanout.md](../benchmarks/03-http-fanout.md).

## 04-json-roundtrip (serialization + allocator)

Stresses the serde / `encoding/json` hot path, allocator churn on small
irregular objects, and the host→guest HTTP-body copy across the WASI
boundary — a microservice hot path that none of 01-03 exercises. The
k6 harness sweeps the request array length `N` over
`[100, 1000, 10000, 100000]` and emits a dedicated `n_sweep.png` line
chart showing throughput-vs-N per variant.

```bash
# Defaults: limited threads, 20 VUs, 30 s per N, sweep [100, 1000, 10000, 100000]
./benchmarks/04-json-roundtrip/run_experiment.sh

# Scaling experiment, full sweep:
./benchmarks/04-json-roundtrip/run_experiment.sh \
    --scaling-experiment both \
    --users 20 \
    --duration 30s \
    --ns "100 1000 10000 100000"
```

Workload spec: [../benchmarks/04-json-roundtrip.md](../benchmarks/04-json-roundtrip.md).

## What each orchestrator does, step by step

1. **Sequential teardown** — deletes sibling example namespaces (see
   [sequential-example-model.md](sequential-example-model.md))
2. **Deploy** — applies the `k8s/<example>/` manifests; waits for pods
3. **Health checks** — verifies all four variants respond on `/health`
4. **Load tests** — runs k6 per variant; saves `<variant>_summary.json`
   and `<variant>_k6.json` under `results/<example>/<mode>/`
5. **Prometheus metrics** — queries memory + CPU per variant against the
   in-cluster Prometheus
6. **Cold + warm start** — scales each deployment 0→1; run 1 = cold,
   runs 2–N = warm; saves `cold_start.json` + `warm_start.json`
7. **Image sizes** — Docker variants via `docker inspect`, Spin variants
   via `.wasm` artefact size; saved as `image_sizes.json`
8. **Binary sizes** — raw binary or `.wasm` extracted per variant;
   saved as `binary_sizes.json` (see
   [../reference/notes-on-metrics.md](../reference/notes-on-metrics.md))
9. **Chart generation** — calls `analyze.py --mode <mode>` to render PNGs

For the output layout and how to regenerate charts without re-running,
see [output-structure.md](output-structure.md).

For the limited vs unlimited mode mechanics, see
[scaling-modes.md](scaling-modes.md).
