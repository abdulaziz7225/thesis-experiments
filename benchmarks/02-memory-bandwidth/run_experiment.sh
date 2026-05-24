#!/usr/bin/env bash
# ============================================================
# run_experiment.sh – Orchestrate the full 02-memory-bandwidth run
# ============================================================
#
# SEQUENTIAL EXECUTION MODEL:
#   Only one benchmark example may be active at a time (shared NodePorts).
#   This script tears down the previous example namespace (if any) and
#   deploys 02-memory-bandwidth before running any measurements.
#
# USAGE:
#   export THESIS_NODE_IP=<hetzner-server-ip>
#   export KUBECONFIG=<path-to>/hetzner-thesis.yaml
#   ./run_experiment.sh [--users 50] [--ramp 20s] [--duration 60s] \
#                       [--size-kb 64] [--cold-start-runs 6] \
#                       [--scaling-experiment limited|unlimited|both]
#
# WHAT IT DOES:
#   0. Tears down prime-sieve namespace; deploys 02-memory-bandwidth.
#   1. Verifies all four primary variants are healthy (wasm-rust, wasm-tinygo, docker-rust, docker-golang).
#   2. Runs k6 load tests sequentially (one variant at a time).
#      After each run, queries Prometheus for memory/CPU metrics.
#   3. Runs cold-start AND warm-start measurements (--mode both).
#   4. Collects OCI image sizes via local docker inspect (falls back to manual prompt).
#   5. Calls analyze.py to generate individual charts.
#   (Optional) scaling-experiment: repeat steps 2-3 with unlimited threads/instances.
#
# OUTPUT: results/02-memory-bandwidth/
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}/../.."
RESULTS_DIR="${SCRIPT_DIR}/../../results/02-memory-bandwidth"
mkdir -p "${RESULTS_DIR}"

# ── Defaults ──────────────────────────────────────────────────────────────────
VUS=50
RAMP="20s"
DURATION="60s"
SIZE_KB=64
COLD_START_RUNS=6
SCALING_EXP="limited"

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --users)               VUS="$2";             shift 2 ;;
    --ramp)                RAMP="$2";            shift 2 ;;
    --duration)            DURATION="$2";        shift 2 ;;
    --size-kb)             SIZE_KB="$2";         shift 2 ;;
    --cold-start-runs)     COLD_START_RUNS="$2"; shift 2 ;;
    --scaling-experiment)  SCALING_EXP="$2";     shift 2 ;;
    *) echo "Unknown arg: $1" && exit 1 ;;
  esac
done

# ── Guards ────────────────────────────────────────────────────────────────────
: "${THESIS_NODE_IP:?Set THESIS_NODE_IP to the Hetzner server public IP}"
: "${KUBECONFIG:?Set KUBECONFIG to the path of hetzner-thesis.yaml}"

command -v k6      >/dev/null || { echo "k6 not found – run 'make setup-local' in thesis-infra-setup/"; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
command -v kubectl >/dev/null || { echo "kubectl not found"; exit 1; }

# ── Variant map: name → NodePort ─────────────────────────────────────────────
# Primary 4-variant matrix:
#   Wasm (SpinKube / Wasmtime-Cranelift): 30081-30082 (pod port 80)
#   Docker (runc/native):                             30083-30084 (pod port 8080)
declare -A PORTS=(
  ["wasm-rust"]=30081
  ["wasm-tinygo"]=30082
  ["docker-rust"]=30083
  ["docker-golang"]=30084
)

# ── Helper: wait for HTTP health ──────────────────────────────────────────────
wait_healthy() {
  local url="$1"
  local tries=0
  echo -n "    Waiting for ${url}/health "
  until curl -sf "${url}/health" >/dev/null 2>&1; do
    echo -n "."
    sleep 2
    (( tries++ ))
    if (( tries > 60 )); then
      echo " TIMEOUT"
      return 1
    fi
  done
  echo " OK"
}

# ── Step 0: Sequential deployment ─────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 0: Sequential deployment"
echo "══════════════════════════════════════════"

echo "  Tearing down sibling example namespaces if running..."
kubectl delete namespace prime-sieve    --ignore-not-found=true || true
kubectl delete namespace http-fanout    --ignore-not-found=true || true
kubectl delete namespace json-roundtrip --ignore-not-found=true || true

echo "  Deploying 02-memory-bandwidth manifests..."
kubectl apply -f "${REPO_ROOT}/k8s/02-memory-bandwidth/namespace.yaml"
kubectl apply -f "${REPO_ROOT}/k8s/02-memory-bandwidth/"
echo "  Waiting for pods to be ready (60 s)..."
sleep 30
kubectl wait --for=condition=Ready pods --all -n memory-bandwidth --timeout=120s || true

# ── Step 1: Health checks ─────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 1: Health checks"
echo "══════════════════════════════════════════"
for variant in wasm-rust wasm-tinygo docker-rust docker-golang; do
  port="${PORTS[$variant]}"
  url="http://${THESIS_NODE_IP}:${port}"
  wait_healthy "${url}" || { echo "  WARN: ${variant} is not healthy – skipping"; }
done

# ── Run k6 + Prometheus for a given scaling mode ──────────────────────────────
run_load_tests() {
  local mode="$1"
  local results_subdir="${RESULTS_DIR}/${mode}"
  mkdir -p "${results_subdir}"

  echo ""
  echo "── k6 load tests [mode=${mode}] ──"
  for variant in wasm-rust wasm-tinygo docker-rust docker-golang; do
    port="${PORTS[$variant]}"
    url="http://${THESIS_NODE_IP}:${port}"
    echo "  Running k6 for ${variant} (port ${port})..."

    # Collect idle/baseline memory before the load test.
    python3 "${SCRIPT_DIR}/prometheus_metrics.py" \
      --variant "${variant}" \
      --idle-only 2>&1 | sed 's/^/    /' || echo "  WARN: Prometheus query failed (continuing)"

    START_TS=$(date +%s)

    k6 run \
      --env BASE_URL="${url}" \
      --env VARIANT="${variant}" \
      --env VUS="${VUS}" \
      --env RAMP="${RAMP}" \
      --env DURATION="${DURATION}" \
      --env SIZE_KB="${SIZE_KB}" \
      --env NO_HASH="0" \
      --summary-export="${results_subdir}/${variant}_summary.json" \
      --out "json=${results_subdir}/${variant}_k6.json" \
      "${SCRIPT_DIR}/k6-load-test.js" \
      2>&1 | tail -20

    END_TS=$(date +%s)

    python3 "${SCRIPT_DIR}/prometheus_metrics.py" \
      --variant "${variant}" \
      --start "${START_TS}" \
      --end   "${END_TS}" \
      2>&1 | sed 's/^/    /' || echo "  WARN: Prometheus query failed (continuing)"
  done
}

apply_thread_limits() {
  echo "  Applying single-thread constraints..."
  for variant in docker-rust docker-golang; do
    if [[ "${variant}" == "docker-rust" ]]; then
      kubectl set env deployment/memory-bandwidth-docker-rust TOKIO_WORKER_THREADS=1 -n memory-bandwidth
    else
      kubectl set env deployment/memory-bandwidth-docker-golang GOMAXPROCS=1 -n memory-bandwidth
    fi
  done
  for variant in wasm-rust wasm-tinygo; do
    local name="memory-bandwidth-${variant}"
    kubectl patch spinapp "${name}" -n memory-bandwidth --type=merge \
      -p '{"spec":{"replicas":1}}' 2>/dev/null || true
  done
  sleep 10
}

apply_unlimited_threads() {
  echo "  Removing thread constraints (unlimited mode)..."
  for variant in docker-rust docker-golang; do
    if [[ "${variant}" == "docker-rust" ]]; then
      kubectl set env deployment/memory-bandwidth-docker-rust TOKIO_WORKER_THREADS=4 -n memory-bandwidth
    else
      kubectl set env deployment/memory-bandwidth-docker-golang GOMAXPROCS=4 -n memory-bandwidth
    fi
  done
  for variant in wasm-rust wasm-tinygo; do
    local name="memory-bandwidth-${variant}"
    kubectl patch spinapp "${name}" -n memory-bandwidth --type=merge \
      -p '{"spec":{"replicas":4}}' 2>/dev/null || true
  done
  sleep 15
}

# ── Step 2: Load tests ────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 2: Load tests"
echo "  vus=${VUS}  duration=${DURATION}  size-kb=${SIZE_KB}"
echo "══════════════════════════════════════════"

if [[ "${SCALING_EXP}" == "limited" || "${SCALING_EXP}" == "both" ]]; then
  apply_thread_limits
  run_load_tests "limited"
fi

if [[ "${SCALING_EXP}" == "unlimited" || "${SCALING_EXP}" == "both" ]]; then
  apply_unlimited_threads
  run_load_tests "unlimited"
  # Restore to limited for cold-start measurements
  apply_thread_limits
fi

# ── Step 3: Cold-start + warm-start measurements ──────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 3: Cold-start + warm-start measurements"
echo "  total cycles per variant: ${COLD_START_RUNS}"
echo "  (run 1 = cold, runs 2-${COLD_START_RUNS} = warm)"
echo "══════════════════════════════════════════"

python3 "${SCRIPT_DIR}/cold_start.py" \
  --runs "${COLD_START_RUNS}" \
  --mode both

# ── Step 4: OCI image sizes ───────────────────────────────────────────────────
IMAGE_SIZES_FILE="${RESULTS_DIR}/image_sizes.json"
echo ""
echo "══════════════════════════════════════════"
echo "  Step 4: OCI image sizes"
echo "══════════════════════════════════════════"

if [[ ! -f "${IMAGE_SIZES_FILE}" ]]; then
  if command -v docker >/dev/null 2>&1; then
    echo "  Reading local image sizes via docker inspect …"
    python3 - "${IMAGE_SIZES_FILE}" <<'PYEOF'
import json, subprocess, sys, os

out_path = sys.argv[1]

docker_images = {
    "docker.io/abdulaziz7225/memory-bandwidth-docker-rust:latest":   "docker-rust",
    "docker.io/abdulaziz7225/memory-bandwidth-docker-golang:latest": "docker-golang",
}

spin_wasm_paths = {
    "wasm-rust":   "wasm/rust/02-memory-bandwidth/target/wasm32-wasip1/release/memory_bandwidth_spin.wasm",
    "wasm-tinygo": "wasm/tinygo/02-memory-bandwidth/app.wasm",
}

sizes = {}

for image, variant in docker_images.items():
    result = subprocess.run(
        ["docker", "inspect", "--format={{.Size}}", image],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        sizes[variant] = round(int(result.stdout.strip()) / 1_048_576, 2)

# out_path is <repo_root>/results/02-memory-bandwidth/image_sizes.json
# dirname → <repo_root>/results/02-memory-bandwidth  →  ../..  →  <repo_root>
repo_root = os.path.abspath(os.path.join(os.path.dirname(out_path), "../.."))
for variant, rel_path in spin_wasm_paths.items():
    wasm_path = os.path.join(repo_root, rel_path)
    if os.path.isfile(wasm_path):
        sizes[variant] = round(os.path.getsize(wasm_path) / 1_048_576, 2)
    else:
        print(f"  WARN: {rel_path} not found – build first")

if sizes:
    with open(out_path, "w") as f:
        json.dump(sizes, f, indent=2)
    print(f"  Saved {out_path}")
    for k, v in sizes.items():
        print(f"    {k}: {v} MB")
    if len(sizes) < 4:
        missing = [v for v in list(docker_images.values()) + list(spin_wasm_paths.keys()) if v not in sizes]
        print(f"  NOTE: {len(sizes)}/4 sizes collected. Missing: {missing}")
else:
    print("  ERROR: no image sizes collected – skipping image_sizes.json")
PYEOF
  fi
fi

if [[ ! -f "${IMAGE_SIZES_FILE}" ]]; then
  echo ""
  echo "  Could not collect image sizes automatically."
  echo "  For Docker variants: docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep memory-bandwidth"
  echo "  For Spin variants: du -sh wasm/rust/02-memory-bandwidth/target/wasm32-wasip1/release/memory_bandwidth_spin.wasm"
  echo "                     du -sh wasm/tinygo/02-memory-bandwidth/app.wasm"
  echo '  Then create: {"wasm-rust":<MB>,"wasm-tinygo":<MB>,"docker-rust":<MB>,"docker-golang":<MB>}'
fi

# ── Step 4b: Binary artifact sizes (raw .wasm / scratch binary) ──────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 4b: Binary artifact sizes"
echo "══════════════════════════════════════════"
python3 "${SCRIPT_DIR}/../shared/binary_sizes.py" \
  --example 02-memory-bandwidth 2>&1 | sed 's/^/    /' \
  || echo "  WARN: binary size collection failed (continuing)"

# ── Step 5: Generate charts ───────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 5: Generating charts"
echo "══════════════════════════════════════════"

for mode in limited unlimited; do
  if [[ "${SCALING_EXP}" == "${mode}" || "${SCALING_EXP}" == "both" ]]; then
    python3 "${SCRIPT_DIR}/analyze.py" --mode "${mode}" \
      2>&1 | sed 's/^/    /'
  fi
done

echo ""
echo "Done!  Results in ${RESULTS_DIR}/"
echo "  limited/   or unlimited/  – per-variant k6 summaries"
echo "  cold_start.json           – cold-start timings (run 1)"
echo "  warm_start.json           – warm-start timings (runs 2+)"
echo "  resource_metrics.json     – memory + CPU from Prometheus"
echo "  image_sizes.json          – OCI image sizes"
