# thesis-experiments

Benchmark experiments comparing Docker vs. WebAssembly (WasmEdge) microservice runtimes.
Four variants of the same prime-sieve HTTP service are deployed to a k3s cluster and load-tested.

| Variant | Runtime | Language | HTTP layer | NodePort |
|---------|---------|----------|------------|----------|
| `docker-rust` | runc (OCI) | Rust 1.94 | axum (async, tokio) | 30083 |
| `docker-golang` | runc (OCI) | Go 1.26 | net/http stdlib | 30084 |
| `wasm-rust` | WasmEdge 0.14.1 via crun 1.22 | Rust 1.94 | wasmedge\_wasi\_socket (sync) | 30081 |
| `wasm-tinygo` | WasmEdge 0.14.1 via crun 1.22 | TinyGo 0.34.0 | raw TCP (wasmedge socket ext., sync) | 30082 |

> **Prerequisites:** complete the infrastructure provisioning in `../thesis-infra-setup/`
> before running any step here.

---

## Repository layout

```
thesis-experiments/
├── docker/
│   ├── rust/01-prime-sieve/        # Docker + Rust (axum)
│   └── golang/01-prime-sieve/      # Docker + Go (net/http)
├── wasm/
│   ├── rust/01-prime-sieve/        # WASM + Rust (wasmedge_wasi_socket)
│   └── tinygo/01-prime-sieve/      # WASM + TinyGo 0.34.0 (direct WasmEdge socket imports)
├── k8s/01-prime-sieve/             # Kubernetes manifests
├── benchmarks/01-prime-sieve/      # Locust load tests + analysis scripts
└── results/01-prime-sieve/         # Output directory (git-ignored)
```

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

> Run once after cloning, and again whenever application code changes.
> Replace `abdulaziz7225` with your Docker Hub username if different.

```bash
export DOCKER_USER=abdulaziz7225

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

# WASM + TinyGo  (uses TinyGo 0.34.0 — see wasm/tinygo/01-prime-sieve/Dockerfile)
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
```
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

curl -s http://${IP}:30081/health          # wasm-rust   → (empty body, 200)
curl -s http://${IP}:30082/health          # wasm-tinygo → ok
curl -s http://${IP}:30083/health          # docker-rust → (empty body, 200)
curl -s http://${IP}:30084/health          # docker-golang → ok

# Functional check
curl -s "http://${IP}:30081/sieve?limit=100&no_list=0" | python3 -m json.tool
curl -s "http://${IP}:30082/sieve?limit=100&no_list=0" | python3 -m json.tool
curl -s "http://${IP}:30083/sieve?limit=100&no_list=0" | python3 -m json.tool
curl -s "http://${IP}:30084/sieve?limit=100&no_list=0" | python3 -m json.tool
```

---

## Phase 4 — Run the benchmark

```bash
source .venv/bin/activate

export THESIS_NODE_IP=<server-ip>
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml

# Default run (50 users, 60 s, limit=100 000)
./benchmarks/01-prime-sieve/run_experiment.sh

# Custom run
./benchmarks/01-prime-sieve/run_experiment.sh \
    --users 100         \
    --spawn-rate 20     \
    --duration 120s     \
    --limit 1000000     \
    --cold-start-runs 10
```

Results are written to `results/01-prime-sieve/`:
```
results/01-prime-sieve/
├── wasm-rust_stats.csv        # Locust raw stats
├── wasm-rust.html             # Locust HTML report
├── wasm-tinygo_stats.csv
├── wasm-tinygo.html
├── docker-rust_stats.csv
├── docker-rust.html
├── docker-golang_stats.csv
├── docker-golang.html
├── cold_start.json            # Cold-start timing per variant
├── image_sizes.json           # (manual — see below)
└── comparison.png             # Generated comparison chart
```

### Image sizes (manual step)

The analysis script needs image sizes. Run this on the machine where you built the images:

```bash
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep prime-sieve
```

Create `results/01-prime-sieve/image_sizes.json`:
```json
{
  "wasm-rust":     <MB as float>,
  "wasm-tinygo":   <MB as float>,
  "docker-rust":   <MB as float>,
  "docker-golang": <MB as float>
}
```

Then regenerate the chart:
```bash
python3 benchmarks/01-prime-sieve/analyze.py \
    --out results/01-prime-sieve/comparison.png
```

---

## Observability

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | `http://<IP>:32000` | admin / thesis-grafana |
| Prometheus | `http://<IP>:32090` | — |

---

## Re-running the experiment

### After code changes (rebuild images)

```bash
# Rebuild only what changed, e.g. wasm-rust
docker build -t docker.io/abdulaziz7225/prime-sieve-wasm-rust:latest \
    wasm/rust/01-prime-sieve/
docker push docker.io/abdulaziz7225/prime-sieve-wasm-rust:latest

# Force pods to pull the new :latest image
kubectl rollout restart deployment/prime-sieve-wasm-rust -n prime-sieve
kubectl rollout status  deployment/prime-sieve-wasm-rust -n prime-sieve
```

### After re-provisioning the VM (new server IP)

```bash
cd ../thesis-infra-setup

make configure   # fetches new kubeconfig with updated IP
make label-node
make deploy-stack
make test        # smoke-test WasmEdge runtime

cd ../thesis-experiments

export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
export THESIS_NODE_IP=$(cd ../thesis-infra-setup && terraform output -raw instance_public_ip)

kubectl apply -f k8s/01-prime-sieve/namespace.yaml
kubectl apply -f k8s/01-prime-sieve/docker-rust.yaml
kubectl apply -f k8s/01-prime-sieve/docker-golang.yaml
kubectl apply -f k8s/01-prime-sieve/wasm-rust.yaml
kubectl apply -f k8s/01-prime-sieve/wasm-tinygo.yaml
kubectl get pods -n prime-sieve -w
```

### Clean slate on the same server (delete + redeploy)

```bash
kubectl delete namespace prime-sieve
kubectl apply -f k8s/01-prime-sieve/namespace.yaml
kubectl apply -f k8s/01-prime-sieve/docker-rust.yaml
kubectl apply -f k8s/01-prime-sieve/docker-golang.yaml
kubectl apply -f k8s/01-prime-sieve/wasm-rust.yaml
kubectl apply -f k8s/01-prime-sieve/wasm-tinygo.yaml
kubectl get pods -n prime-sieve -w
```

---

## Debugging

```bash
# Pod status
kubectl get pods -n prime-sieve -o wide

# Logs for a crashing pod
kubectl logs -n prime-sieve <pod-name>
kubectl logs -n prime-sieve <pod-name> --previous   # last crashed instance

# Detailed events (ImagePullBackOff, OOMKilled, etc.)
kubectl describe pod -n prime-sieve <pod-name>

# SSH into server for low-level inspection
ssh -i ~/.ssh/id_hetzner_cloud root@${THESIS_NODE_IP}

# On server: verify WasmEdge + crun setup
crun --version             # must include +WASM:wasmedge
wasmedge --version         # must show 0.14.1
cat /var/log/thesis-setup.log   # full cloud-init log

# On server: check containerd runtime config
cat /var/lib/rancher/k3s/agent/etc/containerd/config.toml | grep -A10 wasmedge
```

---

## Tear down

### Remove only the experiment workloads (keep VM running)

```bash
kubectl delete namespace prime-sieve
# Observability stack stays; VM stays running (costs money)
```

### Destroy the VM completely (stop Hetzner billing)

```bash
cd ../thesis-infra-setup
make teardown
# Deletes the Hetzner server, firewall, and local hetzner-thesis.yaml
# All data on the VM is lost — images are safe on Docker Hub
```

> After teardown, re-provisioning starts again from **Phase 2**.

---

## Toolchain version reference

| Component | Version | Pinned? | Reason |
|-----------|---------|---------|--------|
| k3s | v1.35.2+k3s1 | cloud-init.sh | Latest stable (Jan 2026) |
| WasmEdge | 0.14.1 | cloud-init.sh | Latest stable |
| crun | 1.22 | cloud-init.sh | Latest stable with `--with-wasmedge` |
| Rust (Docker) | 1.94 | Dockerfile | Current stable |
| Rust (WASM) | 1.94 | Dockerfile | Current stable |
| Go (Docker) | 1.26 | Dockerfile | Current stable |
| TinyGo (WASM) | 0.34.0 | Dockerfile | net/http unusable on wasip1 for any TinyGo version; uses direct //go:wasmimport socket calls instead (see wasm/tinygo/README.md) |
| wasmedge\_wasi\_socket | 0.5.5 | Cargo.toml | Latest; `std::net` is unimplemented for wasm32-wasip1 |
