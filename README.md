# Master Thesis Experiments

Benchmark experiments comparing Docker vs. WebAssembly microservice runtimes.
Four variants of each benchmark workload are deployed to a k3s cluster and load-tested.

**Primary 4-variant matrix (all using the same NodePorts):**

| Variant         | Runtime                                             | Language      | HTTP layer                              | NodePort |
| --------------- | --------------------------------------------------- | ------------- | --------------------------------------- | -------- |
| `wasm-rust`     | SpinKube / Wasmtime-Cranelift (WASI Preview 2 (P2)) | Rust 1.94     | spin-sdk `#[http_component]` (async)    | 30081    |
| `wasm-tinygo`   | SpinKube / Wasmtime-Cranelift (wasip1)              | TinyGo 0.40.1 | `spinhttp.Handle()` (net/http style)    | 30082    |
| `docker-rust`   | runc (OCI)                                          | Rust 1.94     | axum (async, tokio)                     | 30083    |
| `docker-golang` | runc (OCI)                                          | Go 1.26       | net/http stdlib                         | 30084    |

---

## Repository layout

```text
thesis-experiments/
├── docker/
│   ├── rust/
│   │   ├── 01-prime-sieve/               # Docker + Rust (axum): Sieve of Eratosthenes
│   │   └── 02-memory-bandwidth/          # Docker + Rust (axum): in-memory I/O + SHA-256
│   └── golang/
│       ├── 01-prime-sieve/               # Docker + Go (net/http): Sieve of Eratosthenes
│       └── 02-memory-bandwidth/          # Docker + Go (net/http): in-memory I/O + SHA-256
├── wasm/
│   ├── rust/
│   │   ├── 01-prime-sieve/       # Spin/Rust (WASI P2 component): Sieve
│   │   └── 02-memory-bandwidth/          # Spin/Rust (WASI P2 component): I/O + SHA-256
│   ├── tinygo/
│   │   ├── 01-prime-sieve/       # Spin/TinyGo (wasip1): Sieve
│   │   └── 02-memory-bandwidth/          # Spin/TinyGo (wasip1): I/O + SHA-256
│   └── wasmedge/                 # Optional WASI Preview 1 (P1) variants (see Appendix B)
│       ├── rust/01-prime-sieve/
│       └── tinygo/01-prime-sieve/
├── k8s/
│   ├── 01-prime-sieve/           # K8s manifests (namespace: prime-sieve)
│   │   ├── namespace.yaml
│   │   ├── wasm-rust.yaml        # SpinApp CRD, nodePort 30081
│   │   ├── wasm-tinygo.yaml      # SpinApp CRD, nodePort 30082
│   │   ├── docker-rust.yaml      # Deployment + Service, nodePort 30083
│   │   ├── docker-golang.yaml    # Deployment + Service, nodePort 30084
│   │   └── optional/             # WasmEdge variants (30085-30086)
│   └── 02-memory-bandwidth/              # K8s manifests (namespace: memory-bandwidth)
│       ├── namespace.yaml
│       ├── wasm-rust.yaml        # nodePort 30081
│       ├── wasm-tinygo.yaml      # nodePort 30082
│       ├── docker-rust.yaml      # nodePort 30083
│       ├── docker-golang.yaml    # nodePort 30084
│       └── optional/
├── benchmarks/
│   ├── shared/utils.py           # Shared helpers (VARIANTS, VARIANT_LABELS, Prometheus, kubectl)
│   ├── 01-prime-sieve/           # k6 load tests + analysis for prime-sieve
│   └── 02-memory-bandwidth/              # k6 load tests + analysis for memory-bandwidth
└── results/                      # Output directory (git-ignored)
    ├── 01-prime-sieve/
    └── 02-memory-bandwidth/
```

### Benchmark scripts (per example)

| File                    | Purpose                                                                          |
| ----------------------- | -------------------------------------------------------------------------------- |
| `k6-load-test.js`       | k6 load-test script — 50 VUs, configurable duration, custom server metric        |
| `cold_start.py`         | Cold (run 1) and warm (runs 2+) start by scaling deployments 0 → 1              |
| `prometheus_metrics.py` | Queries Prometheus for memory/CPU per variant over a load-test window            |
| `analyze.py`            | Reads result files and generates chart PNGs (`--mode limited\|unlimited`)        |
| `run_experiment.sh`     | Master orchestrator — health checks, load tests, cold start, image sizes, charts |

---

## Sequential Example Model

All benchmark examples reuse the same NodePorts (30081–30084).
**Only one example may be active at a time.** Each `run_experiment.sh` automatically
tears down the previous example's namespace before deploying its own:

```bash
# run_experiment.sh for 02-memory-bandwidth does this automatically:
kubectl delete namespace prime-sieve --ignore-not-found
kubectl apply -f k8s/02-memory-bandwidth/
```

To switch manually:

```bash
# Tear down 01-prime-sieve
kubectl delete namespace prime-sieve

# Deploy 02-memory-bandwidth
kubectl apply -f k8s/02-memory-bandwidth/namespace.yaml
kubectl apply -f k8s/02-memory-bandwidth/
```

---

## Phase 0 — Local prerequisites (once)

```bash
# Python virtualenv for benchmarks
cd thesis-experiments
python3 -m venv .venv
source .venv/bin/activate
pip install -r benchmarks/requirements.txt

# Docker (for building Docker images)
docker info   # verify daemon is running

# Spin CLI (for building and pushing Spin/WASI P2 OCI images)
curl -fsSL https://developer.fermyon.com/downloads/install.sh | bash
spin --version   # v3+

# cargo-component (for Rust WASI P2 components)
cargo install cargo-component

# kubectl pointing to the Hetzner cluster (set after infra is up)
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
```

---

## Phase 1 — Build and push all images

```bash
export DOCKER_USER=<YOUR_DOCKERHUB_USERNAME>

# ── Docker variants (standard OCI, docker push) ────────────────────────────────

# Docker + Rust
docker build -t docker.io/${DOCKER_USER}/prime-sieve-docker-rust:latest \
    docker/rust/01-prime-sieve/
docker push docker.io/${DOCKER_USER}/prime-sieve-docker-rust:latest

# Docker + Go
docker build -t docker.io/${DOCKER_USER}/prime-sieve-docker-golang:latest \
    docker/golang/01-prime-sieve/
docker push docker.io/${DOCKER_USER}/prime-sieve-docker-golang:latest

# ── Wasm variants (WASI P2 OCI, spin registry push) ───────────────────────────
# Wasm images use Spin-specific OCI media types — use `spin registry push`, NOT docker push.

# Wasm + Rust (01-prime-sieve)
cd wasm/rust/01-prime-sieve
cargo component build --release
spin registry push \
    --build \
    docker.io/${DOCKER_USER}/prime-sieve-wasm-rust:latest
cd ../../..

# Wasm + TinyGo (01-prime-sieve)
cd wasm/tinygo/01-prime-sieve
tinygo build -target=wasip1 -gc=conservative -opt=2 -o app.wasm .
spin registry push docker.io/${DOCKER_USER}/prime-sieve-wasm-tinygo:latest
cd ../../..

# ── 02-memory-bandwidth variants (same pattern) ────────────────────────────────────────

docker build -t docker.io/${DOCKER_USER}/memory-bandwidth-docker-rust:latest \
    docker/rust/02-memory-bandwidth/
docker push docker.io/${DOCKER_USER}/memory-bandwidth-docker-rust:latest

docker build -t docker.io/${DOCKER_USER}/memory-bandwidth-docker-golang:latest \
    docker/golang/02-memory-bandwidth/
docker push docker.io/${DOCKER_USER}/memory-bandwidth-docker-golang:latest

cd wasm/rust/02-memory-bandwidth
cargo component build --release
spin registry push docker.io/${DOCKER_USER}/memory-bandwidth-wasm-rust:latest
cd ../../..

cd wasm/tinygo/02-memory-bandwidth
tinygo build -target=wasip1 -gc=conservative -opt=2 -o app.wasm .
spin registry push docker.io/${DOCKER_USER}/memory-bandwidth-wasm-tinygo:latest
cd ../../..
```

---

## Phase 2 — Infrastructure is ready (infra-setup side)

These steps live in `../thesis-infra-setup/` and must be completed **before** deploying here.

```bash
cd ../thesis-infra-setup

# 1. Provision the Hetzner VM (Terraform + cloud-init: k3s + SpinKube)
make up

# 2. Wait for cloud-init and fetch kubeconfig (~5-8 min)
make configure

# 3. Label the node so the SpinKube RuntimeClass can schedule pods
make label-node

# 4. Deploy cert-manager, SpinOperator, Prometheus, Grafana
make deploy-stack

# 5. Smoke-test: verifies Spin/Wasmtime can run a SpinApp at all
make test
# Expected: HTTP 200 from hello-spin SpinApp

cd ../thesis-experiments
```

---

## Phase 3 — Deploy an experiment

```bash
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
export THESIS_NODE_IP=$(cd ../thesis-infra-setup && terraform output -raw instance_public_ip)

# Deploy 01-prime-sieve (creates namespace prime-sieve)
kubectl apply -f k8s/01-prime-sieve/namespace.yaml
kubectl apply -f k8s/01-prime-sieve/

# Watch until all pods reach Ready (30-90 s)
kubectl get pods -n prime-sieve -w
```

Expected steady state:

```text
NAME                                          READY   STATUS    RESTARTS
prime-sieve-docker-golang-xxx                 1/1     Running   0
prime-sieve-docker-rust-xxx                   1/1     Running   0
prime-sieve-wasm-rust-xxx                     1/1     Running   0
prime-sieve-wasm-tinygo-xxx                   1/1     Running   0
```

### Quick smoke-test

```bash
IP=${THESIS_NODE_IP}

# Health checks
curl -s http://${IP}:30081/health          # wasm-rust
curl -s http://${IP}:30082/health          # wasm-tinygo
curl -s http://${IP}:30083/health          # docker-rust
curl -s http://${IP}:30084/health          # docker-golang

# Functional check (01-prime-sieve)
curl -s "http://${IP}:30081/sieve?limit=100&no_list=0" | python3 -m json.tool
curl -s "http://${IP}:30082/sieve?limit=100&no_list=0" | python3 -m json.tool
curl -s "http://${IP}:30083/sieve?limit=100&no_list=0" | python3 -m json.tool
curl -s "http://${IP}:30084/sieve?limit=100&no_list=0" | python3 -m json.tool

# Functional check (02-memory-bandwidth, after switching examples)
curl -s "http://${IP}:30081/membw?size_kb=64" | python3 -m json.tool
```

---

## Phase 4 — Run the benchmark

### 01-prime-sieve

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

### 02-memory-bandwidth

```bash
# run_experiment.sh tears down prime-sieve first automatically
./benchmarks/02-memory-bandwidth/run_experiment.sh

./benchmarks/02-memory-bandwidth/run_experiment.sh \
    --scaling-experiment both \
    --size-kb 64 \
    --users 50 \
    --duration 60s
```

### Scaling experiment

Both orchestrators accept `--scaling-experiment limited|unlimited|both` (default: `limited`):

- **`limited`** — GOMAXPROCS=1, TOKIO_WORKER_THREADS=1 for Docker variants; replicas=1 for Spin.
  Isolates single-threaded throughput; ensures the WASI P2 request-handler model is not penalised
  by comparing against an unrestricted multi-core Docker variant.
- **`unlimited`** — GOMAXPROCS=2, TOKIO_WORKER_THREADS=2 for Docker; replicas=4 for Spin.
  Shows how each variant exploits parallelism.
- **`both`** — runs limited first, then unlimited, then restores limited for cold-start measurements.

Results for each mode go to `results/<example>/limited/` or `results/<example>/unlimited/`.

### Step-by-step flow

1. **Health checks** — verifies all four variants are reachable
2. **k6 load tests** — runs each variant sequentially; saves to `results/<example>/<mode>/`
3. **Prometheus metrics** — queries memory/CPU per variant after each k6 run
4. **Cold + warm start** — scales each deployment 0 → 1; run 1 = cold, runs 2–N = warm
5. **Image sizes** — Docker variants via `docker inspect`; Spin variants via `.wasm` artifact size
6. **Chart generation** — calls `analyze.py --mode <mode>` to produce PNGs

### Output structure

```text
results/01-prime-sieve/
├── limited/
│   ├── wasm-rust_summary.json
│   ├── wasm-rust_k6.json
│   ├── wasm-tinygo_summary.json  ...
│   └── charts/
├── unlimited/                    (if --scaling-experiment unlimited|both)
│   └── charts/
├── cold_start.json
├── warm_start.json
├── resource_metrics.json
└── image_sizes.json
```

### Regenerate charts without re-running

```bash
python3 benchmarks/01-prime-sieve/analyze.py --mode limited
python3 benchmarks/01-prime-sieve/analyze.py --mode unlimited
```

---

## Observability

| Service    | URL                 | Credentials            |
| ---------- | ------------------- | ---------------------- |
| Grafana    | `http://<IP>:32000` | admin / thesis-grafana |
| Prometheus | `http://<IP>:32090` | —                      |

Relevant Prometheus queries:

```promql
# Memory RSS per variant (prime-sieve)
container_memory_rss{namespace="prime-sieve"}

# CPU usage rate
rate(container_cpu_usage_seconds_total{namespace="prime-sieve"}[30s])
```

---

## Tear down

```bash
# Remove active experiment workloads (keep VM running)
kubectl delete namespace prime-sieve   # or memory-bandwidth

# Destroy the VM completely
cd ../thesis-infra-setup
make teardown
```

---

## Toolchain version reference

| Component                   | Version       | Pinned?            | Notes                                                      |
| --------------------------- | ------------- | ------------------ | ---------------------------------------------------------- |
| k3s                         | v1.35.2+k3s1  | cloud-init.sh      | Latest stable                                              |
| containerd-shim-spin-v2     | v0.17.0       | cloud-init.sh      | SpinKube Wasm shim (Wasmtime/Cranelift)                    |
| SpinOperator                | v0.6.1        | Makefile (Helm)    | Manages SpinApp CRDs; requires cert-manager                |
| cert-manager                | v1.16.3       | Makefile (Helm)    | Prerequisite for SpinOperator webhooks                     |
| Spin CLI                    | v3+           | local install      | `spin registry push` for WASI P2 OCI images               |
| cargo-component             | latest        | local install      | Builds Rust WASI P2 components (`cargo component build`)   |
| k6                          | latest stable | setup-local target | Load testing tool                                          |
| Rust (Docker + Spin)        | 1.94          | Dockerfile         | Current stable                                             |
| Go (Docker)                 | 1.26          | Dockerfile         | Current stable                                             |
| TinyGo (Spin)               | 0.40.1        | Dockerfile / local | `-target=wasip1`; wasip2 hardwires wasi:cli/command world  |
| spin-sdk (Rust)             | 5.2.0         | Cargo.toml         | `#[http_component]` macro for WASI P2 HTTP handlers        |
| spin-go-sdk (TinyGo)        | v2.2.1        | go.mod             | Official Spin Go SDK; exports fermyon:spin/inbound-http    |

---

## Optional: WasmEdge (WASI P1) comparison

WasmEdge variants run at ports 30085–30086 and require `ENABLE_WASMEDGE=true` during provisioning.
See `k8s/01-prime-sieve/optional/` for manifests and Appendix B of the thesis report for
benchmark results and the motivation for switching to SpinKube as the primary runtime.

```bash
# Provision with WasmEdge support
ENABLE_WASMEDGE=true make up   # in thesis-infra-setup/

# Label node for WasmEdge
make label-node-wasmedge

# Deploy optional variants
kubectl apply -f k8s/01-prime-sieve/optional/
```
