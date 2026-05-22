# Master Thesis Experiments

Benchmark experiments comparing Docker vs. WebAssembly microservice runtimes.
Four variants of each benchmark workload are deployed to a Kubernetes cluster (kubeadm) and load-tested.

Four complementary workloads, each exercising a different cost dimension of the
runtime + language combination:

| Example               | Workload class                | Hot path                                                           |
| --------------------- | ----------------------------- | ------------------------------------------------------------------ |
| `01-prime-sieve`      | **CPU-bound**                 | Integer compute (Sieve of Eratosthenes)                            |
| `02-memory-bandwidth` | **memory-bound**              | Bulk heap allocation + SHA-256 over a configurable buffer          |
| `03-http-fanout`      | **I/O-bound**                 | N concurrent outbound HTTP GETs to an in-cluster `io-echo` backend |
| `04-json-roundtrip`   | **serialization + allocator** | Parse a posted JSON integer array, sort, aggregate, re-serialise   |

**Primary 4-variant matrix (all using the same NodePorts):**

| Variant         | Runtime                                 | Language      | HTTP layer                           | NodePort |
| --------------- | --------------------------------------- | ------------- | ------------------------------------ | -------- |
| `wasm-rust`     | SpinKube / Wasmtime-Cranelift (WASI P2) | Rust 1.94     | spin-sdk `#[http_component]` (async) | 30081    |
| `wasm-tinygo`   | SpinKube / Wasmtime-Cranelift (WASI P1) | TinyGo 0.40.0 | `spinhttp.Handle()` (net/http style) | 30082    |
| `docker-rust`   | runc (OCI)                              | Rust 1.94     | axum (async, tokio)                  | 30083    |
| `docker-golang` | runc (OCI)                              | Go 1.26       | net/http stdlib                      | 30084    |

---

## Repository layout

```text
thesis-experiments/
├── backend/
│   └── io-echo/                          # Tiny Go HTTP backend with configurable delay (used by 03-http-fanout)
├── docker/
│   ├── rust/
│   │   ├── 01-prime-sieve/               # Docker + Rust (axum): Sieve of Eratosthenes        – CPU-bound
│   │   ├── 02-memory-bandwidth/          # Docker + Rust (axum): in-memory I/O + SHA-256       – memory-bound
│   │   ├── 03-http-fanout/               # Docker + Rust (axum + reqwest): outbound HTTP fan-out – I/O-bound
│   │   └── 04-json-roundtrip/            # Docker + Rust (axum + serde): JSON parse / transform – serialization
│   └── golang/
│       ├── 01-prime-sieve/               # Docker + Go (net/http): Sieve of Eratosthenes        – CPU-bound
│       ├── 02-memory-bandwidth/          # Docker + Go (net/http): in-memory I/O + SHA-256       – memory-bound
│       ├── 03-http-fanout/               # Docker + Go (net/http + goroutines): outbound HTTP fan-out – I/O-bound
│       └── 04-json-roundtrip/            # Docker + Go (net/http + encoding/json): JSON parse / transform – serialization
├── wasm/
│   ├── rust/
│   │   ├── 01-prime-sieve/               # Spin/Rust (WASI P2): Sieve                          – CPU-bound
│   │   ├── 02-memory-bandwidth/          # Spin/Rust (WASI P2): I/O + SHA-256                  – memory-bound
│   │   ├── 03-http-fanout/               # Spin/Rust (WASI P2): outbound HTTP fan-out          – I/O-bound
│   │   └── 04-json-roundtrip/            # Spin/Rust (WASI P2): JSON parse / transform         – serialization
│   └── tinygo/
│       ├── 01-prime-sieve/               # Spin/TinyGo (WASI P1): Sieve                        – CPU-bound
│       ├── 02-memory-bandwidth/          # Spin/TinyGo (WASI P1): I/O + SHA-256                – memory-bound
│       ├── 03-http-fanout/               # Spin/TinyGo (WASI P1): outbound HTTP fan-out        – I/O-bound
│       └── 04-json-roundtrip/            # Spin/TinyGo (WASI P1): JSON parse / transform       – serialization
├── k8s/
│   ├── 01-prime-sieve/                   # K8s manifests (namespace: prime-sieve)         – CPU-bound
│   ├── 02-memory-bandwidth/              # K8s manifests (namespace: memory-bandwidth)    – memory-bound
│   ├── 03-http-fanout/                   # K8s manifests (namespace: http-fanout)         – I/O-bound (+ io-echo backend)
│   └── 04-json-roundtrip/                # K8s manifests (namespace: json-roundtrip)      – serialization
├── benchmarks/
│   ├── shared/utils.py                   # Shared helpers (VARIANTS, VARIANT_LABELS, Prometheus, kubectl)
│   ├── 01-prime-sieve/                   # k6 load tests + analysis for prime-sieve (CPU-bound)
│   ├── 02-memory-bandwidth/              # k6 load tests + analysis for memory-bandwidth
│   ├── 03-http-fanout/                   # k6 load tests + analysis for http-fanout (I/O-bound)
│   └── 04-json-roundtrip/                # k6 N-sweep load tests + analysis for json-roundtrip
└── results/                              # Output directory (git-ignored)
    ├── 01-prime-sieve/
    ├── 02-memory-bandwidth/
    ├── 03-http-fanout/
    └── 04-json-roundtrip/
```

### Benchmark scripts (per example)

| File                    | Purpose                                                                          |
| ----------------------- | -------------------------------------------------------------------------------- |
| `k6-load-test.js`       | k6 load-test script — 50 VUs, configurable duration, custom server metric        |
| `cold_start.py`         | Cold (run 1) and warm (runs 2+) start by scaling deployments 0 → 1               |
| `prometheus_metrics.py` | Queries Prometheus for memory/CPU per variant over a load-test window            |
| `analyze.py`            | Reads result files and generates chart PNGs (`--mode limited\|unlimited`)        |
| `run_experiment.sh`     | Master orchestrator — health checks, load tests, cold start, image sizes, charts |

---

## Sequential Example Model

All four benchmark examples reuse the same NodePorts (30081–30084).
**Only one example may be active at a time.** Each `run_experiment.sh` automatically
tears down the sibling example namespaces before deploying its own:

```bash
# run_experiment.sh for 03-http-fanout does this automatically:
kubectl delete namespace prime-sieve      --ignore-not-found
kubectl delete namespace memory-bandwidth --ignore-not-found
kubectl delete namespace json-roundtrip   --ignore-not-found
kubectl apply -f k8s/03-http-fanout/
```

To switch manually:

```bash
# Tear down whatever is running
kubectl delete namespace prime-sieve memory-bandwidth http-fanout json-roundtrip --ignore-not-found

# Deploy 03-http-fanout (the I/O-bound example, including the io-echo backend)
kubectl apply -f k8s/03-http-fanout/namespace.yaml
kubectl apply -f k8s/03-http-fanout/
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

# TinyGo + Go 1.23.12 SDK (REQUIRED for the wasm-tinygo variants)
# TinyGo 0.40.1 rejects Go >= 1.26, and Go 1.24/1.25 trigger crypto/sha256 panics
# inside the TinyGo runtime on wasip1. Go 1.23.12 is the only known-good version.
# Install it via the official "go get" SDK manager (does not affect the system Go):
go install golang.org/dl/go1.23.12@latest
go1.23.12 download
# go1.23.12 lands in ~/sdk/go1.23.12 — the Phase 1 tinygo build commands prepend
# that directory to PATH so TinyGo invokes the right Go toolchain.

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

# ── Wasm variants (SpinKube OCI, spin registry push) ──────────────────────────
# Wasm images use Spin-specific OCI media types — use `spin registry push`, NOT docker push.
#
# Wasm + TinyGo note: TinyGo 0.40.1 rejects Go >= 1.26 and Go 1.24/1.25 trigger
# crypto/sha256 panics inside the TinyGo wasip1 runtime. The build commands below
# prepend ~/sdk/go1.23.12/bin to PATH so TinyGo picks up the known-good Go 1.23.12
# toolchain (installed in Phase 0). The Wasm + Rust commands are unaffected.

# Wasm + Rust (01-prime-sieve)
cd wasm/rust/01-prime-sieve
cargo component build --release
spin registry push \
    --build \
    docker.io/${DOCKER_USER}/prime-sieve-wasm-rust:latest
cd ../../..

# Wasm + TinyGo (01-prime-sieve)
cd wasm/tinygo/01-prime-sieve
PATH="$HOME/sdk/go1.23.12/bin:$PATH" \
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
PATH="$HOME/sdk/go1.23.12/bin:$PATH" \
  tinygo build -target=wasip1 -gc=conservative -opt=2 -o app.wasm .
spin registry push docker.io/${DOCKER_USER}/memory-bandwidth-wasm-tinygo:latest
cd ../../..

# ── 03-http-fanout variants (I/O-bound; also needs the io-echo backend image) ────

# I/O target pod — built ONCE, reused by the four 03 variants for outbound HTTP.
docker build -t docker.io/${DOCKER_USER}/io-echo-backend:latest backend/io-echo/
docker push  docker.io/${DOCKER_USER}/io-echo-backend:latest

docker build -t docker.io/${DOCKER_USER}/http-fanout-docker-rust:latest \
    docker/rust/03-http-fanout/
docker push docker.io/${DOCKER_USER}/http-fanout-docker-rust:latest

docker build -t docker.io/${DOCKER_USER}/http-fanout-docker-golang:latest \
    docker/golang/03-http-fanout/
docker push docker.io/${DOCKER_USER}/http-fanout-docker-golang:latest

cd wasm/rust/03-http-fanout
cargo component build --release
spin registry push docker.io/${DOCKER_USER}/http-fanout-wasm-rust:latest
cd ../../..

cd wasm/tinygo/03-http-fanout
PATH="$HOME/sdk/go1.23.12/bin:$PATH" \
  tinygo build -target=wasip1 -gc=conservative -opt=2 -o app.wasm .
spin registry push docker.io/${DOCKER_USER}/http-fanout-wasm-tinygo:latest
cd ../../..

# ── 04-json-roundtrip variants (serialization / allocator hot path) ──────────

docker build -t docker.io/${DOCKER_USER}/json-roundtrip-docker-rust:latest \
    docker/rust/04-json-roundtrip/
docker push docker.io/${DOCKER_USER}/json-roundtrip-docker-rust:latest

docker build -t docker.io/${DOCKER_USER}/json-roundtrip-docker-golang:latest \
    docker/golang/04-json-roundtrip/
docker push docker.io/${DOCKER_USER}/json-roundtrip-docker-golang:latest

cd wasm/rust/04-json-roundtrip
cargo component build --release
spin registry push docker.io/${DOCKER_USER}/json-roundtrip-wasm-rust:latest
cd ../../..

cd wasm/tinygo/04-json-roundtrip
PATH="$HOME/sdk/go1.23.12/bin:$PATH" \
  tinygo build -target=wasip1 -gc=conservative -opt=2 -o app.wasm .
spin registry push docker.io/${DOCKER_USER}/json-roundtrip-wasm-tinygo:latest
cd ../../..
```

---

## Phase 2 — Infrastructure is ready (infra-setup side)

These steps live in `../thesis-infra-setup/` and must be completed **before** deploying here.

```bash
cd ../thesis-infra-setup

# 1. Provision the Hetzner VM (Terraform + cloud-init: kubeadm + SpinKube)
make up

# 2. Wait for cloud-init and fetch kubeconfig (~5-8 min)
make configure

# 3. Label the node so the SpinKube RuntimeClass can schedule pods
make label

# 4. Deploy cert-manager, SpinOperator, Prometheus, Grafana
make deploy

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

# Deploy 02-memory-bandwidth
kubectl apply -f k8s/02-memory-bandwidth/namespace.yaml
kubectl apply -f k8s/02-memory-bandwidth/

# Watch until all pods reach Ready (30-90 s)
kubectl get pods -n memory-bandwidth -w
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

# Functional check (03-http-fanout, I/O-bound, after switching examples)
# Each variant dispatches n=3 concurrent outbound GETs to io-echo (10 ms each):
curl -s "http://${IP}:30081/fanout?n=3&delay_ms=10&no_list=0" | python3 -m json.tool
curl -s "http://${IP}:30082/fanout?n=3&delay_ms=10&no_list=0" | python3 -m json.tool

# Functional check (04-json-roundtrip, after switching examples)
curl -s -X POST -H 'Content-Type: application/json' \
  -d '[5,1,4,2,3]' \
  "http://${IP}:30081/jsontx?no_list=0" | python3 -m json.tool
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
# run_experiment.sh tears down sibling example namespaces first automatically
./benchmarks/02-memory-bandwidth/run_experiment.sh

# Scaling experiment (both limited and unlimited passes)
./benchmarks/02-memory-bandwidth/run_experiment.sh \
    --scaling-experiment both \
    --size-kb 64 \
    --users 50 \
    --duration 60s
```

### 03-http-fanout (I/O-bound)

This example is the I/O-bound counterpart to 01-prime-sieve (CPU-bound) and
02-memory-bandwidth (memory-bound). Each variant exposes
`GET /fanout?n=N&delay_ms=D` and dispatches N concurrent outbound HTTP GETs
to an in-cluster `io-echo` backend Deployment that sleeps for `delay_ms`
before responding; per-request latency is therefore dominated by outbound
I/O wait rather than CPU work. Spin variants use
`spin_sdk::http::send` + `futures::join_all` (Rust) or `spinhttp.Send` +
goroutines (TinyGo); Docker variants use `reqwest` (Rust) and `net/http`
(Go) — the same idiomatic async/concurrent I/O pattern in each ecosystem.

```bash
# run_experiment.sh tears down sibling example namespaces and brings up io-echo
./benchmarks/03-http-fanout/run_experiment.sh

# Scaling experiment, full sweep:
./benchmarks/03-http-fanout/run_experiment.sh \
    --scaling-experiment both \
    --n 5 \
    --delay-ms 50 \
    --users 50 \
    --duration 60s
```

### 04-json-roundtrip

Stresses the serde / `encoding/json` hot path, allocator churn on small
irregular objects, and the host->guest HTTP-body copy across the WASI
boundary — a microservice hot path that none of 01-prime-sieve (integer
compute), 02-memory-bandwidth (bulk memcpy), or 03-http-fanout (outbound
I/O wait) exercises. The k6 harness sweeps the request array length
`N` over `[100, 1000, 10000, 100000]` and emits a dedicated
`n_sweep.png` line chart showing throughput-vs-N per variant.

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

### Scaling experiment

Both orchestrators accept `--scaling-experiment limited|unlimited|both` (default: `limited`):

- **`limited`** — GOMAXPROCS=1, TOKIO_WORKER_THREADS=1 for Docker variants; replicas=1 for Spin.
  Isolates single-threaded throughput; ensures the WASI P2 request-handler model is not penalised
  by comparing against an unrestricted multi-core Docker variant.
- **`unlimited`** — GOMAXPROCS=4, TOKIO_WORKER_THREADS=4 for Docker; replicas=4 for Spin.
  Matches the four physical vCPUs of the Hetzner ccx23 host so that each variant can
  exploit the available parallelism. The K8s `limits.cpu` is set to `4000m` in the
  manifests so cgroup CPU bandwidth control does not throttle the added threads.
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

python3 benchmarks/02-memory-bandwidth/analyze.py --mode limited
python3 benchmarks/02-memory-bandwidth/analyze.py --mode unlimited

python3 benchmarks/03-http-fanout/analyze.py --mode limited
python3 benchmarks/03-http-fanout/analyze.py --mode unlimited

python3 benchmarks/04-json-roundtrip/analyze.py --mode limited
python3 benchmarks/04-json-roundtrip/analyze.py --mode unlimited
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
kubectl delete namespace prime-sieve memory-bandwidth http-fanout json-roundtrip \
  --ignore-not-found

# Destroy the VM completely
cd ../thesis-infra-setup
make teardown
```

---

## Toolchain version reference

| Component               | Version       | Pinned             | Notes                                                     |
| ----------------------- | ------------- | ------------------ | --------------------------------------------------------- |
| Kubernetes (kubeadm)    | v1.34.x       | cloud-init.sh      | Upstream reference platform; Flannel CNI                  |
| containerd-shim-spin-v2 | v0.17.0       | cloud-init.sh      | SpinKube Wasm shim (Wasmtime/Cranelift)                   |
| SpinOperator            | v0.6.1        | Makefile (Helm)    | Manages SpinApp CRDs; requires cert-manager               |
| cert-manager            | v1.16.3       | Makefile (Helm)    | Prerequisite for SpinOperator webhooks                    |
| Spin CLI                | v3+           | local install      | `spin registry push` for WASI P2 OCI images               |
| cargo-component         | latest        | local install      | Builds Rust WASI P2 components (`cargo component build`)  |
| k6                      | latest stable | setup-local target | Load testing tool                                         |
| Rust (Docker + Spin)    | 1.94          | Dockerfile         | Current stable                                            |
| Go (Docker)             | 1.26          | Dockerfile         | Current stable                                            |
| TinyGo (Spin)           | 0.40.0        | Dockerfile / local | `-target=wasip1`; wasip2 hardwires wasi:cli/command world |
| spin-sdk (Rust)         | 5.2.0         | Cargo.toml         | `#[http_component]` macro for WASI P2 HTTP handlers       |
| spin-go-sdk (TinyGo)    | v2.2.1        | go.mod             | Official Spin Go SDK; exports fermyon:spin/inbound-http   |
