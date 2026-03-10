# Master Thesis Experiments

Benchmark experiments comparing Docker vs. WebAssembly (WasmEdge) microservice runtimes.
Four variants of the same prime-sieve HTTP service are deployed to a k3s cluster and load-tested.

| Variant         | Runtime                       | Language      | HTTP layer                           | NodePort |
| --------------- | ----------------------------- | ------------- | ------------------------------------ | -------- |
| `docker-rust`   | runc (OCI)                    | Rust 1.94     | axum (async, tokio)                  | 30083    |
| `docker-golang` | runc (OCI)                    | Go 1.26       | net/http stdlib                      | 30084    |
| `wasm-rust`     | WasmEdge 0.14.1 via crun 1.22 | Rust 1.94     | wasmedge_wasi_socket (sync)          | 30081    |
| `wasm-tinygo`   | WasmEdge 0.14.1 via crun 1.22 | TinyGo 0.40.1 | raw TCP (wasmedge socket ext., sync) | 30082    |

---

## Repository layout

```markdown
thesis-experiments/
├── docker/
│   ├── rust/01-prime-sieve/        # Docker + Rust (axum)
│   └── golang/01-prime-sieve/      # Docker + Go (net/http)
├── wasm/
│   ├── rust/01-prime-sieve/        # WASM + Rust (wasmedge_wasi_socket)
│   └── tinygo/01-prime-sieve/      # WASM + TinyGo 0.40.1 (direct WasmEdge socket imports)
├── k8s/01-prime-sieve/             # Kubernetes manifests
├── benchmarks/01-prime-sieve/      # k6 load tests + analysis scripts
└── results/01-prime-sieve/         # Output directory (git-ignored)
```

### Benchmark scripts

| File                    | Purpose                                                                                |
| ----------------------- | -------------------------------------------------------------------------------------- |
| `k6-load-test.js`       | k6 load-test script — 50 VUs, configurable duration, custom `server_compute_us` metric |
| `cold_start.py`         | Measures cold-start (run 1) and warm-start (runs 2+) by scaling deployments 0 → 1      |
| `prometheus_metrics.py` | Queries Prometheus for memory/CPU per variant over a load-test time window             |
| `analyze.py`            | Reads all result files and generates the multi-panel `comparison.png`                  |
| `run_experiment.sh`     | Master orchestrator — runs all of the above in sequence                                |

---

## Phase 0 — Local prerequisites (once)

```bash
# Python virtualenv for benchmarks
cd thesis-experiments
python3 -m venv .venv
source .venv/bin/activate
pip install -r benchmarks/requirements.txt

# Docker (for building images)
docker info   # verify daemon is running

# kubectl pointing to the Hetzner cluster (set after infra is up)
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
```

---

## Phase 1 — Build and push all four images

```bash
export DOCKER_USER=<YOUR_DOCKERHUB_USERNAME>

# Docker + Rust
docker build -t docker.io/${DOCKER_USER}/prime-sieve-docker-rust:latest \
    docker/rust/01-prime-sieve/
docker push docker.io/${DOCKER_USER}/prime-sieve-docker-rust:latest

# Docker + Go
docker build -t docker.io/${DOCKER_USER}/prime-sieve-docker-golang:latest \
    docker/golang/01-prime-sieve/
docker push docker.io/${DOCKER_USER}/prime-sieve-docker-golang:latest

# WASM + Rust  (cross-compiles to wasm32-wasip1 inside the builder stage)
docker build -t docker.io/${DOCKER_USER}/prime-sieve-wasm-rust:latest \
    wasm/rust/01-prime-sieve/
docker push docker.io/${DOCKER_USER}/prime-sieve-wasm-rust:latest

# WASM + TinyGo  (uses TinyGo 0.40.1 — see wasm/tinygo/01-prime-sieve/Dockerfile)
docker build -t docker.io/${DOCKER_USER}/prime-sieve-wasm-tinygo:latest \
    wasm/tinygo/01-prime-sieve/
docker push docker.io/${DOCKER_USER}/prime-sieve-wasm-tinygo:latest
```

Verify the images were pushed:

```bash
docker images | grep prime-sieve
```

---

## Phase 2 — Infrastructure is ready (infra-setup side)

These steps live in `../thesis-infra-setup/` and must be completed **before** deploying here.

```bash
cd ../thesis-infra-setup

# 1. Provision the Hetzner VM (Terraform + cloud-init: k3s + WasmEdge 0.14.1 + crun 1.22)
make up

# 2. Wait for cloud-init and fetch kubeconfig  (~5-8 min)
make configure

# 3. Label the node so the WasmEdge RuntimeClass can schedule pods
make label-node

# 4. Deploy Prometheus + Grafana + WasmEdge RuntimeClass
make deploy-stack

# 5. Smoke-test: verifies WasmEdge + crun can run a WASM pod at all
make test
# Expected output: random bytes, env vars, "Printed from wasi: ..."

cd ../thesis-experiments
```

---

## Phase 3 — Deploy the experiment

```bash
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
export THESIS_NODE_IP=$(cd ../thesis-infra-setup && terraform output -raw instance_public_ip)

# Apply all manifests
kubectl apply -f k8s/01-prime-sieve/namespace.yaml
kubectl apply -f k8s/01-prime-sieve/docker-rust.yaml
kubectl apply -f k8s/01-prime-sieve/docker-golang.yaml
kubectl apply -f k8s/01-prime-sieve/wasm-rust.yaml
kubectl apply -f k8s/01-prime-sieve/wasm-tinygo.yaml

# Watch until all four pods reach 1/1 Running  (30-90 s)
kubectl get pods -n prime-sieve -w
```

Expected steady state:

```bash
NAME                                       READY   STATUS    RESTARTS
prime-sieve-docker-golang-xxx              1/1     Running   0
prime-sieve-docker-rust-xxx                1/1     Running   0
prime-sieve-wasm-rust-xxx                  1/1     Running   0
prime-sieve-wasm-tinygo-xxx                1/1     Running   0
```

### Quick smoke-test of the services

```bash
# Replace with actual server IP
IP=${THESIS_NODE_IP}

# Health checks
curl -sv http://${IP}:30081/health          # wasm-rust   → HTTP 200
curl -sv http://${IP}:30082/health          # wasm-tinygo → HTTP 200
curl -sv http://${IP}:30083/health          # docker-rust → HTTP 200
curl -sv http://${IP}:30084/health          # docker-golang → HTTP 200

# Functional check — should return JSON with a "primes" array
curl -s "http://${IP}:30081/sieve?limit=100&no_list=0" | python3 -m json.tool
curl -s "http://${IP}:30082/sieve?limit=100&no_list=0" | python3 -m json.tool
curl -s "http://${IP}:30083/sieve?limit=100&no_list=0" | python3 -m json.tool
curl -s "http://${IP}:30084/sieve?limit=100&no_list=0" | python3 -m json.tool
```

---

## Phase 4 — Run the benchmark

```bash
# Default run (50 VUs, 60 s, limit=100 000, 6 start cycles per variant)
./benchmarks/01-prime-sieve/run_experiment.sh

# Custom run
./benchmarks/01-prime-sieve/run_experiment.sh \
    --users 100         \
    --duration 120s     \
    --limit 1000000     \
    --cold-start-runs 8
```

The orchestrator performs these steps in order:

1. **Health checks** — verifies all four variants are reachable
2. **k6 load tests** — runs each variant sequentially; queries Prometheus for memory/CPU after each run
3. **Cold + warm start** — scales each deployment 0 → 1 six times; run 1 = cold start (image pull), runs 2–6 = warm starts (image cached)
4. **Image sizes** — collected automatically via local `docker inspect`; falls back to a manual prompt if Docker is unavailable
5. **Chart generation** — calls `analyze.py` to produce `comparison.png`

Results are written to `results/01-prime-sieve/`:

```markdown
results/01-prime-sieve/
├── wasm-rust_summary.json      # k6 summary (latency p50/p95/p99, RPS, error rate)
├── wasm-rust_k6.json           # k6 time-series (raw, for RPS-over-time panel)
├── wasm-tinygo_summary.json
├── wasm-tinygo_k6.json
├── docker-rust_summary.json
├── docker-rust_k6.json
├── docker-golang_summary.json
├── docker-golang_k6.json
├── cold_start.json             # cold-start timings (run 1 per variant)
├── warm_start.json             # warm-start timings (runs 2+ per variant)
├── resource_metrics.json       # idle memory, peak memory, avg CPU from Prometheus
├── image_sizes.json            # OCI image sizes in MB
└── comparison.png              # generated 9-panel comparison chart
```

### Regenerate the chart without re-running the experiment

```bash
python3 benchmarks/01-prime-sieve/analyze.py \
    --out results/01-prime-sieve/comparison.png
```

### Run individual scripts manually

```bash
# k6 load test for one variant only
k6 run \
    --env BASE_URL=http://${THESIS_NODE_IP}:30081 \
    --env VARIANT=wasm-rust \
    --env VUS=50 \
    --env DURATION=60s \
    --summary-export=results/01-prime-sieve/wasm-rust_summary.json \
    --out json=results/01-prime-sieve/wasm-rust_k6.json \
    benchmarks/01-prime-sieve/k6-load-test.js

# Cold + warm start for one variant only
python3 benchmarks/01-prime-sieve/cold_start.py \
    --variant wasm-rust --runs 6 --mode both

# Prometheus resource metrics for one variant
python3 benchmarks/01-prime-sieve/prometheus_metrics.py \
    --variant wasm-rust \
    --start <unix-ts-start> \
    --end   <unix-ts-end>
```

---

## Observability

| Service    | URL                 | Credentials            |
| ---------- | ------------------- | ---------------------- |
| Grafana    | `http://<IP>:32000` | admin / thesis-grafana |
| Prometheus | `http://<IP>:32090` | —                      |

During a load test, you can watch live metrics in Grafana. The kube-prometheus-stack scrapes at 5 s intervals. Relevant panels to add:

- `container_memory_working_set_bytes{namespace="prime-sieve"}` — RSS per variant
- `rate(container_cpu_usage_seconds_total{namespace="prime-sieve"}[1m])` — CPU usage

---

## Tear down

### Remove only the experiment workloads (keep VM running)

```bash
kubectl delete namespace prime-sieve
```

### Destroy the VM completely (stop Hetzner billing)

```bash
cd ../thesis-infra-setup
make teardown
```

---

## Toolchain version reference

| Component            | Version       | Pinned?                     | Reason                                                                                                                           |
| -------------------- | ------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| k3s                  | v1.35.2+k3s1  | cloud-init.sh               | Latest stable (Jan 2026)                                                                                                         |
| WasmEdge             | 0.14.1        | cloud-init.sh               | Latest stable                                                                                                                    |
| crun                 | 1.22          | cloud-init.sh               | Latest stable with `--with-wasmedge`                                                                                             |
| k6                   | latest stable | setup-local Makefile target | Load testing tool                                                                                                                |
| Rust (Docker)        | 1.94          | Dockerfile                  | Current stable                                                                                                                   |
| Rust (WASM)          | 1.94          | Dockerfile                  | Current stable                                                                                                                   |
| Go (Docker)          | 1.26          | Dockerfile                  | Current stable                                                                                                                   |
| TinyGo (WASM)        | 0.40.1        | Dockerfile                  | net/http unusable on wasip1 for any TinyGo version; uses direct //go:wasmimport socket calls instead (see wasm/tinygo/README.md) |
| wasmedge_wasi_socket | 0.5.5         | Cargo.toml                  | Latest; `std::net` is unimplemented for wasm32-wasip1                                                                            |
