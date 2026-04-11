# Experiment Plan: Kubernetes FaaS Scale-Out Benchmark (Wasm vs Docker, Multi-Cluster)

## Context

The thesis's original proposal is to compare **how fast Wasm and Docker scale in Kubernetes** — specifically FaaS-style scale-to-zero/scale-from-zero behavior across a multi-cluster environment with multiple worker nodes. The existing benchmarks (prime sieve, memory bandwidth) captured isolated runtime performance (RPS, latency, CPU, memory), which is valid supplementary data, but the primary thesis contribution should be Kubernetes-level scaling behavior.

Reference architecture: [aws-samples/serverless-wasm-on-eks](https://github.com/aws-samples/serverless-wasm-on-eks) — uses Knative Serving + RuntimeClass:spin (containerd-shim-spin-v2) + Packer AMIs on EKS. Key insight: **Wasm variants do not need Dockerfiles at runtime**. The Dockerfile in `wasm/*/` is only a BUILD convenience (multi-stage: tinygo/cargo → .wasm → scratch image → `spin registry push`). At runtime, Kubernetes uses `runtimeClassName: spin` → containerd-shim-spin-v2 → Wasmtime/Cranelift. Docker/runc is never in the Wasm execution path.

### Why Wasm should win at scaling (the thesis hypothesis)

| Factor | Wasm (SpinKube) | Docker (runc) |
|---|---|---|
| Image size | 0.19–2.11 MB | 2.08–5.99 MB |
| OCI pull time (cold node) | ~50–500ms | ~1–10s |
| Component instantiation | ~5–50ms (Wasmtime memory-map) | ~500ms–3s (overlay fs + process spawn) |
| Scale-to-zero | Native via KEDA/Knative | Possible but adds HTTP buffering overhead |

The runtime performance benchmarks show Docker winning on RPS/latency — this is expected (Cranelift JIT < LLVM native). The scaling benchmarks should show Wasm winning on startup and scale-out speed.

## Target State

1. **Multi-node Hetzner cluster**: 1 control plane (existing ccx13) + 2–3 worker nodes (new ccx13s via Terraform)
2. **Second cluster**: TU Dresden Kubernetes cluster (KUBECONFIG provided separately)
3. **Scale-to-zero capability**: KEDA HTTP Add-on on both clusters (lighter than Knative+Istio; ~200MB overhead; no service mesh required)
4. **New benchmark 03-scaling**: Proper pod-level scale-out measurement, replacing the flawed cold_start.py 3-second sleep approach
5. **Enhanced benchmarks 01 and 02**: Add scale-out dimensions (scale from 1→N under load)

---

## Architecture Decision: KEDA vs Knative

**Recommendation: KEDA HTTP Add-on** (not Knative+Istio as in the reference repo)

- Istio adds ~2 GB RAM overhead — infeasible on ccx13 workers (8 GB shared with workloads)
- Knative with Kourier is lighter (~800 MB) but still doubles the control plane footprint
- KEDA HTTP Add-on provides identical scale-to-zero semantics with ~200 MB overhead
- KEDA integrates with both standard Deployments AND SpinApp CRD via `spec.minReplicaCount: 0`
  - Note: SpinApp admission webhook rejects `spec.replicas: 0`; KEDA HTTP add-on bypasses this by scaling the underlying Deployment directly (same mechanism already in `utils.py`)
- KEDA is CNCF-graduated, production-grade, and simple to operate on k3s

---

## Part 1: Infrastructure Changes (thesis-infra-setup/)

### 1.1 Add worker nodes to Hetzner — `main.tf`

```hcl
variable "worker_count" {
  default = 2
}

resource "hcloud_server" "k3s_worker" {
  count        = var.worker_count
  name         = "thesis-wasm-worker-${count.index + 1}"
  image        = var.os_image
  server_type  = var.server_type   # ccx13: 2 vCPU, 8 GB — same as control plane
  location     = var.location
  ssh_keys     = [data.hcloud_ssh_key.default.id]
  firewall_ids = [hcloud_firewall.k3s_firewall.id]
  user_data    = templatefile("${path.module}/cloud-init-worker.sh", {
    server_ip = hcloud_server.k3s_node.ipv4_address
  })
}

output "worker_ips" {
  value = hcloud_server.k3s_worker[*].ipv4_address
}
```

The k3s join token must be retrieved from the control plane after provisioning:
```bash
ssh root@${THESIS_NODE_IP} cat /var/lib/rancher/k3s/server/node-token
```

### 1.2 New file: `cloud-init-worker.sh`

```bash
#!/bin/bash
exec > /var/log/thesis-worker-setup.log 2>&1
set -ex

# Install containerd-shim-spin (same version as control plane)
SPIN_SHIM_VERSION="0.17.0"
curl -fsSL \
  "https://github.com/spinframework/containerd-shim-spin/releases/download/v${SPIN_SHIM_VERSION}/containerd-shim-spin-v2-linux-x86_64.tar.gz" \
  | tar -xz -C /usr/local/bin/
chmod +x /usr/local/bin/containerd-shim-spin-v2

# Configure containerd for the spin RuntimeClass
mkdir -p /var/lib/rancher/k3s/agent/etc/containerd
cat > /var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl << 'TMPL'
{{ template "base" . }}

[plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.spin]
  runtime_type = 'io.containerd.spin.v2'
TMPL

# Join the k3s cluster as an agent
curl -sfL https://get.k3s.io | \
  INSTALL_K3S_VERSION="v1.35.2+k3s1" \
  K3S_URL="https://${server_ip}:6443" \
  K3S_TOKEN="$(cat /tmp/k3s-token)" \
  sh -
```

### 1.3 Install KEDA on both clusters

```bash
# Install KEDA core
kubectl apply --server-side \
  -f https://github.com/kedacore/keda/releases/download/v2.16.0/keda-2.16.0.yaml

# Install KEDA HTTP Add-on (scale-to-zero for HTTP workloads)
kubectl apply \
  -f https://github.com/kedacore/http-add-on/releases/download/v0.9.0/keda-add-ons-http-0.9.0.yaml
```

### 1.4 k3s vs kubeadm

Keep k3s for Hetzner — it IS Kubernetes, just lighter. The migration plan in `thesis-infra-setup/k8s-migration-plan.md` exists if TU Dresden requires kubeadm for comparison consistency. For the scaling experiment, k3s vs kubeadm is not a confounding variable (containerd, kubelet, kube-scheduler are identical).

---

## Part 2: New Benchmark — 03-scaling

### 2.1 Directory structure

```
benchmarks/03-scaling/
├── run_experiment.sh     # Orchestrator
├── scale_out.py          # Core scale-out measurement
├── pod_events.py         # Image-pull timing from Kubernetes events
└── analyze.py            # Charts

k8s/03-scaling/
├── wasm-rust.yaml        # SpinApp + KEDA HTTPScaledObject
├── wasm-tinygo.yaml
├── docker-rust.yaml      # Deployment + KEDA HTTPScaledObject
└── docker-golang.yaml
```

### 2.2 Measurements

| Metric | How measured | Why it matters |
|---|---|---|
| **Pod-ready latency** (0→1) | `scale cmd time` → `pod.status.conditions[Ready].lastTransitionTime` | True cold start, no HTTP polling artifact |
| **Image pull time** | Pod events: `Pulling image` → `Successfully pulled image` timestamps | Wasm 0.19MB vs Docker 5.99MB advantage |
| **Scale-out latency** (1→N) | Scale cmd → last pod Ready, N ∈ {2, 4, 8} | Horizontal scaling speed |
| **Scale-from-zero** (KEDA) | First HTTP request → first response round-trip | FaaS cold invocation latency |
| **Time to full capacity** | k6 spike test: burst load → RPS recovery to peak | Real FaaS burst behavior |

### 2.3 Replica configurations

Scale-out tested at N ∈ {1, 2, 4, 8} replicas.
With 3 nodes (1 control plane + 2 workers, each 2 vCPU / 8 GB):
- 8 replicas at 64 Mi requests each = 512 Mi total → fits easily
- 8 replicas at 250m CPU requests each = 2000m total → fits across 3 nodes

### 2.4 Core implementation: `scale_out.py`

```python
#!/usr/bin/env python3
"""Measure Kubernetes pod scale-out latency using condition timestamps (not HTTP polling)."""
import subprocess, json, time, datetime, sys
sys.path.insert(0, "../shared")
from utils import scale_any, VARIANTS, SPINAPP_VARIANTS

NAMESPACE = "scaling-benchmark"

def kubectl(*args):
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, check=True).stdout

def scale_out_latency(variant: str, name: str, from_n: int, to_n: int, timeout=300) -> float:
    """Scale from_n→to_n, return seconds until last pod has Ready=True."""
    # Ensure we start from from_n
    scale_any(variant, name, NAMESPACE, from_n)
    # Wait for all from_n pods to be stable
    if from_n > 0:
        subprocess.run(
            ["kubectl", "rollout", "status", "deployment", name,
             "-n", NAMESPACE, f"--timeout={timeout}s"],
            check=True
        )

    t_cmd = datetime.datetime.utcnow()
    scale_any(variant, name, NAMESPACE, to_n)

    deadline = time.time() + timeout
    while time.time() < deadline:
        out = kubectl("get", "pods", "-n", NAMESPACE,
                      "-l", f"app={name}", "-o", "json")
        pods = json.loads(out)["items"]
        ready_pods = [
            p for p in pods
            if any(c["type"] == "Ready" and c["status"] == "True"
                   for c in p.get("status", {}).get("conditions", []))
        ]
        if len(ready_pods) >= to_n:
            # Use the latest Ready timestamp among all pods
            ready_times = []
            for p in ready_pods:
                for c in p["status"]["conditions"]:
                    if c["type"] == "Ready" and c["status"] == "True":
                        ready_times.append(
                            datetime.datetime.fromisoformat(
                                c["lastTransitionTime"].replace("Z", "+00:00")
                            )
                        )
            t_ready = max(ready_times).replace(tzinfo=None)
            return (t_ready - t_cmd).total_seconds()
        time.sleep(0.2)
    raise TimeoutError(f"Only {len(ready_pods)}/{to_n} pods Ready after {timeout}s")
```

### 2.5 Image pull timing: `pod_events.py`

```python
import subprocess, json, datetime

def image_pull_duration(namespace: str, pod_name: str) -> float | None:
    """Return seconds from 'Pulling image' to 'Successfully pulled image' for a pod."""
    out = subprocess.run(
        ["kubectl", "get", "events", "-n", namespace,
         "--field-selector", f"involvedObject.name={pod_name}",
         "-o", "json"],
        capture_output=True, text=True, check=True
    ).stdout
    events = json.loads(out)["items"]

    pulling = next((e for e in events if "Pulling image" in e.get("message", "")), None)
    pulled  = next((e for e in events if "Successfully pulled" in e.get("message", "")), None)

    if pulling and pulled:
        t0 = datetime.datetime.fromisoformat(pulling["lastTimestamp"].replace("Z", "+00:00"))
        t1 = datetime.datetime.fromisoformat(pulled["lastTimestamp"].replace("Z", "+00:00"))
        return (t1 - t0).total_seconds()
    return None
```

### 2.6 Kubernetes manifests: KEDA HTTPScaledObject

**`k8s/03-scaling/wasm-rust.yaml`** (SpinApp + HTTPScaledObject):

```yaml
apiVersion: core.spinkube.dev/v1alpha1
kind: SpinApp
metadata:
  name: scaling-wasm-rust
  namespace: scaling-benchmark
spec:
  image: docker.io/abdulaziz7225/prime-sieve-wasm-rust:latest
  executor: containerd-shim-spin
  replicas: 1
  resources:
    requests: { cpu: "250m", memory: "64Mi" }
    limits:   { cpu: "500m", memory: "128Mi" }
---
apiVersion: http.keda.sh/v1alpha1
kind: HTTPScaledObject
metadata:
  name: scaling-wasm-rust
  namespace: scaling-benchmark
spec:
  hosts: ["scaling-wasm-rust.local"]
  pathPrefixes: ["/"]
  scaleTargetRef:
    name: scaling-wasm-rust
    kind: Deployment        # KEDA targets the Deployment that SpinOperator creates
  replicas:
    min: 0
    max: 16
  scaledownPeriod: 30       # seconds idle before scale-to-zero
```

**`k8s/03-scaling/docker-golang.yaml`** (standard Deployment + HTTPScaledObject):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: scaling-docker-golang
  namespace: scaling-benchmark
spec:
  replicas: 1
  selector:
    matchLabels: { app: scaling-docker-golang }
  template:
    metadata:
      labels: { app: scaling-docker-golang }
    spec:
      containers:
        - name: server
          image: docker.io/abdulaziz7225/prime-sieve-docker-golang:latest
          ports: [{ containerPort: 8080 }]
          env: [{ name: GOMAXPROCS, value: "2" }]  # unlimited mode for scale-out
          resources:
            requests: { cpu: "250m", memory: "64Mi" }
            limits:   { cpu: "500m", memory: "128Mi" }
---
apiVersion: http.keda.sh/v1alpha1
kind: HTTPScaledObject
metadata:
  name: scaling-docker-golang
  namespace: scaling-benchmark
spec:
  hosts: ["scaling-docker-golang.local"]
  pathPrefixes: ["/"]
  scaleTargetRef:
    name: scaling-docker-golang
    kind: Deployment
  replicas:
    min: 0
    max: 16
  scaledownPeriod: 30
```

---

## Part 3: Fix Existing cold_start.py

The current measurement is invalid for Wasm variants because SpinOperator reconciles during the 3-second sleep, and for docker-rust because Axum graceful shutdown serves from the old pod.

### Fix: use pod deletion instead of scale-to-0, and API timestamps instead of HTTP polling

```python
def measure_cold_start(variant: str, name: str, namespace: str) -> float:
    """True cold start: delete the running pod and measure time until new pod is Ready."""
    # Get current pod name
    pods_json = kubectl("get", "pods", "-n", namespace,
                        "-l", f"app={name}", "-o", "json")
    old_pods = {p["metadata"]["name"] for p in json.loads(pods_json)["items"]}

    # Delete the pod (kubelet will create a new one per the Deployment spec)
    t_cmd = datetime.datetime.utcnow()
    for pod_name in old_pods:
        kubectl("delete", "pod", pod_name, "-n", namespace, "--grace-period=0")

    # Wait for a NEW pod (different name) to be Ready
    deadline = time.time() + 180
    while time.time() < deadline:
        pods_json = kubectl("get", "pods", "-n", namespace,
                            "-l", f"app={name}", "-o", "json")
        pods = json.loads(pods_json)["items"]
        new_ready = [
            p for p in pods
            if p["metadata"]["name"] not in old_pods
            and any(c["type"] == "Ready" and c["status"] == "True"
                    for c in p.get("status", {}).get("conditions", []))
        ]
        if new_ready:
            for c in new_ready[0]["status"]["conditions"]:
                if c["type"] == "Ready" and c["status"] == "True":
                    t_ready = datetime.datetime.fromisoformat(
                        c["lastTransitionTime"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    return (t_ready - t_cmd).total_seconds()
        time.sleep(0.1)
    raise TimeoutError("New pod not Ready within 180s")
```

For **image-cold** measurement, add a `--cold` flag that runs before each cycle:
```bash
# Remove image from each node before cold run
for node_ip in ${WORKER_IPS}; do
  ssh root@${node_ip} "crictl rmi docker.io/abdulaziz7225/${IMAGE}:latest 2>/dev/null || true"
done
```

---

## Part 4: Multi-Cluster Experiment

Deploy identical workloads to both Hetzner and TU Dresden clusters, run `scale_out.py` against each KUBECONFIG, compare scale-out latency:

```bash
export KUBECONFIG_HETZNER=../thesis-infra-setup/hetzner-thesis.yaml
export KUBECONFIG_TUDRESDEN=<path-to-tu-dresden-kubeconfig>

# Hetzner
KUBECONFIG=${KUBECONFIG_HETZNER} python3 benchmarks/03-scaling/scale_out.py \
  --cluster hetzner \
  --replicas 1 2 4 8 \
  --output results/03-scaling/hetzner_scale_out.json

# TU Dresden
KUBECONFIG=${KUBECONFIG_TUDRESDEN} python3 benchmarks/03-scaling/scale_out.py \
  --cluster tudresden \
  --replicas 1 2 4 8 \
  --output results/03-scaling/tudresden_scale_out.json
```

Chart output: side-by-side scale-out latency comparison across clusters and variants.

---

## Part 5: Thesis Narrative

The expanded experiment answers three research questions:

1. **Image distribution speed**: How much faster is OCI image pull for Wasm (0.19 MB) vs Docker (5.99 MB) on a cold node? → `pod_events.py` image pull timing
2. **Pod startup speed**: How much faster does a Wasm component instantiate vs a Docker container start, excluding image pull? → pod-ready latency minus image pull time
3. **Horizontal scale-out efficiency**: As N grows from 1→8, does Wasm's time-to-full-capacity grow slower than Docker's? → scale-out latency vs replica count chart

The existing runtime benchmarks (RPS, latency, CPU, memory) provide the counterpoint: Wasm pays a runtime performance cost (≈23% slower RPS, 10× more idle memory due to Wasmtime overhead) in exchange for these scaling advantages.

---

## Implementation Order

1. **Terraform worker nodes** — provision 2 ccx13 workers, join to k3s cluster
2. **KEDA installation** — deploy to Hetzner cluster (verify ScaledObjects work)
3. **k8s/03-scaling/ manifests** — write SpinApp + HTTPScaledObject for all 4 variants
4. **benchmarks/03-scaling/ scripts** — scale_out.py, pod_events.py, analyze.py, run_experiment.sh
5. **Fix cold_start.py** — replace sleep+HTTP-poll with pod-delete + API timestamp approach
6. **Add scale-out phase to 01 and 02** — update run_experiment.sh and analyze.py in both
7. **TU Dresden cluster** — configure SpinKube + KEDA, run same benchmark
8. **LaTeX chapters** — update methodology, implementation, evaluation

## Critical Files

| File | Action |
|---|---|
| `thesis-infra-setup/main.tf` | Add `hcloud_server.k3s_worker` resource |
| `thesis-infra-setup/cloud-init-worker.sh` | New: k3s agent join + containerd-shim-spin |
| `thesis-infra-setup/variables.tf` | Add `worker_count` variable |
| `benchmarks/03-scaling/scale_out.py` | New: core measurement |
| `benchmarks/03-scaling/pod_events.py` | New: image pull timing |
| `benchmarks/03-scaling/analyze.py` | New: scale-out charts |
| `benchmarks/03-scaling/run_experiment.sh` | New: orchestrator |
| `k8s/03-scaling/*.yaml` | New: SpinApp/Deployment + HTTPScaledObject manifests |
| `benchmarks/01-prime-sieve/cold_start.py` | Fix measurement method |
| `benchmarks/02-memory-bandwidth/cold_start.py` | Fix measurement method |
| `benchmarks/01-prime-sieve/run_experiment.sh` | Add scale-out phase |
| `benchmarks/02-memory-bandwidth/run_experiment.sh` | Add scale-out phase |
| `benchmarks/shared/utils.py` | Add `pod_ready_timestamps()` and `image_pull_duration()` |
| `wasm-vs-docker/chapters/04_methodology.tex` | Add multi-cluster + FaaS experiment design |
| `wasm-vs-docker/chapters/05_implementation.tex` | Document KEDA, multi-node Terraform |
| `wasm-vs-docker/chapters/06_evaluation.tex` | New sections: scale-out latency, image pull, cluster comparison |

## Verification Checklist

```bash
# 1. Worker nodes joined
kubectl get nodes -o wide
# Expected: 3 nodes (1 control-plane + 2 workers), all Ready

# 2. KEDA running
kubectl get pods -n keda
# Expected: keda-operator + keda-http-add-on pods Running

# 3. Scale-to-zero works
kubectl get pods -n scaling-benchmark
# After 30s idle: 0 pods

# 4. Scale-from-zero (Wasm should respond in <1s, Docker in ~5-10s)
time curl "http://${THESIS_NODE_IP}:30081/health"
kubectl get pods -n scaling-benchmark -w

# 5. Scale-out benchmark dry run
python3 benchmarks/03-scaling/scale_out.py --replicas 1 2 4 --mode warm --dry-run

# 6. Image-cold measurement
python3 benchmarks/03-scaling/scale_out.py --replicas 1 --mode cold
# Expected: Wasm pull ~0.1-0.5s, Docker pull ~2-8s

# 7. Multi-cluster
KUBECONFIG=${KUBECONFIG_TUDRESDEN} kubectl get nodes
python3 benchmarks/03-scaling/scale_out.py --cluster tudresden --replicas 1 2 4 8
```
