#!/usr/bin/env bash
# ============================================================
# run_experiment.sh – Orchestrate the full 03-http-fanout run
#
# Workload class: I/O-BOUND (outbound HTTP fan-out).
# Each variant forwards every inbound request into N concurrent outbound HTTP
# GETs against an in-cluster io-echo backend; the backend sleeps for delay_ms
# before responding, so throughput is gated by outbound I/O wait — the
# I/O-bound counterpart to 01-prime-sieve (CPU-bound) and 02-memory-bandwidth
# (memory-bound).
# ============================================================
#
# SEQUENTIAL EXECUTION MODEL:
#   Only one benchmark example may be active at a time (shared NodePorts
#   30081-30084). This script tears down the previous example namespace
#   (if any) and deploys 03-http-fanout, including the io-echo backend,
#   before running any measurements.
#
# USAGE:
#   export THESIS_NODE_IP=<hetzner-server-ip>
#   export KUBECONFIG=<path-to>/hetzner-thesis.yaml
#   ./run_experiment.sh [--users 50] [--ramp 20s] [--duration 60s] \
#                       [--n 5] [--delay-ms 50] [--cold-start-runs 6] \
#                       [--scaling-experiment limited|unlimited|both]
#
# WHAT IT DOES:
#   0. Tears down prime-sieve / memory-bandwidth / json-roundtrip namespaces
#      and deploys 03-http-fanout (including io-echo backend).
#   1. Verifies all four primary variants AND the io-echo backend are healthy.
#   2. Runs k6 load tests sequentially (one variant at a time).
#      After each run, queries Prometheus for memory/CPU metrics.
#   3. Runs cold-start AND warm-start measurements (--mode both).
#   4. Collects OCI image sizes via local docker inspect (falls back to manual).
#   5. Calls analyze.py to generate individual charts.
#   (Optional) scaling-experiment: repeat steps 2-3 with unlimited threads/instances.
#
# OUTPUT: results/03-http-fanout/
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}/../.."
RESULTS_DIR="${SCRIPT_DIR}/../../results/03-http-fanout"
mkdir -p "${RESULTS_DIR}"

# ── Defaults ──────────────────────────────────────────────────────────────────
VUS=50
RAMP="20s"
DURATION="60s"
N=5
DELAY_MS=50
COLD_START_RUNS=6
SCALING_EXP="limited"

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --users)               VUS="$2";             shift 2 ;;
    --ramp)                RAMP="$2";            shift 2 ;;
    --duration)            DURATION="$2";        shift 2 ;;
    --n)                   N="$2";               shift 2 ;;
    --delay-ms)            DELAY_MS="$2";        shift 2 ;;
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
echo "  Step 0: Sequential deployment (I/O-bound experiment)"
echo "══════════════════════════════════════════"

echo "  Tearing down previous examples if running..."
kubectl delete namespace prime-sieve      --ignore-not-found=true || true
kubectl delete namespace memory-bandwidth --ignore-not-found=true || true
kubectl delete namespace json-roundtrip   --ignore-not-found=true || true

echo "  Deploying 03-http-fanout manifests (including io-echo backend)..."
kubectl apply -f "${REPO_ROOT}/k8s/03-http-fanout/namespace.yaml"
kubectl apply -f "${REPO_ROOT}/k8s/03-http-fanout/"
echo "  Waiting for pods to be ready (60 s)..."
sleep 30
kubectl wait --for=condition=Ready pods --all -n http-fanout --timeout=180s || true

# ── Step 1: Health checks ─────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 1: Health checks (variants + io-echo backend)"
echo "══════════════════════════════════════════"
for variant in wasm-rust wasm-tinygo docker-rust docker-golang; do
  port="${PORTS[$variant]}"
  url="http://${THESIS_NODE_IP}:${port}"
  wait_healthy "${url}" || { echo "  WARN: ${variant} is not healthy – skipping"; }
done
echo "  io-echo backend reachability (in-cluster, no NodePort exposed)…"
kubectl -n http-fanout wait --for=condition=Available deployment/io-echo --timeout=120s \
  || echo "  WARN: io-echo Deployment not yet Available"

# ── Run k6 + Prometheus for a given scaling mode ──────────────────────────────
run_load_tests() {
  local mode="$1"
  local results_subdir="${RESULTS_DIR}/${mode}"
  mkdir -p "${results_subdir}"

  echo ""
  echo "── k6 load tests [mode=${mode}, workload=io-bound] ──"
  for variant in wasm-rust wasm-tinygo docker-rust docker-golang; do
    port="${PORTS[$variant]}"
    url="http://${THESIS_NODE_IP}:${port}"
    echo "  Running k6 for ${variant} (port ${port}, n=${N}, delay_ms=${DELAY_MS})..."

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
      --env N="${N}" \
      --env DELAY_MS="${DELAY_MS}" \
      --env NO_LIST="1" \
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
      kubectl set env deployment/http-fanout-docker-rust TOKIO_WORKER_THREADS=1 -n http-fanout
    else
      kubectl set env deployment/http-fanout-docker-golang GOMAXPROCS=1 -n http-fanout
    fi
  done
  for variant in wasm-rust wasm-tinygo; do
    local name="http-fanout-${variant}"
    kubectl patch spinapp "${name}" -n http-fanout --type=merge \
      -p '{"spec":{"replicas":1}}' 2>/dev/null || true
  done
  sleep 10
}

apply_unlimited_threads() {
  echo "  Removing thread constraints (unlimited mode)..."
  for variant in docker-rust docker-golang; do
    if [[ "${variant}" == "docker-rust" ]]; then
      kubectl set env deployment/http-fanout-docker-rust TOKIO_WORKER_THREADS=4 -n http-fanout
    else
      kubectl set env deployment/http-fanout-docker-golang GOMAXPROCS=4 -n http-fanout
    fi
  done
  for variant in wasm-rust wasm-tinygo; do
    local name="http-fanout-${variant}"
    kubectl patch spinapp "${name}" -n http-fanout --type=merge \
      -p '{"spec":{"replicas":4}}' 2>/dev/null || true
  done
  sleep 15
}

# ── Step 2: Load tests ────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 2: Load tests (I/O-bound)"
echo "  vus=${VUS}  duration=${DURATION}  n=${N}  delay_ms=${DELAY_MS}"
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
    "docker.io/abdulaziz7225/http-fanout-docker-rust:latest":   "docker-rust",
    "docker.io/abdulaziz7225/http-fanout-docker-golang:latest": "docker-golang",
}

spin_wasm_paths = {
    "wasm-rust":   "wasm/rust/03-http-fanout/target/wasm32-wasip1/release/http_fanout_spin.wasm",
    "wasm-tinygo": "wasm/tinygo/03-http-fanout/app.wasm",
}

sizes = {}

for image, variant in docker_images.items():
    result = subprocess.run(
        ["docker", "inspect", "--format={{.Size}}", image],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        sizes[variant] = round(int(result.stdout.strip()) / 1_048_576, 2)

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
  echo "  For Docker variants: docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep http-fanout"
  echo "  For Spin variants: du -sh wasm/rust/03-http-fanout/target/wasm32-wasip1/release/http_fanout_spin.wasm"
  echo "                     du -sh wasm/tinygo/03-http-fanout/app.wasm"
  echo '  Then create: {"wasm-rust":<MB>,"wasm-tinygo":<MB>,"docker-rust":<MB>,"docker-golang":<MB>}'
fi

# ── Step 4b: Binary artifact sizes (raw .wasm / scratch binary) ──────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 4b: Binary artifact sizes"
echo "══════════════════════════════════════════"
python3 "${SCRIPT_DIR}/../shared/binary_sizes.py" \
  --example 03-http-fanout 2>&1 | sed 's/^/    /' \
  || echo "  WARN: binary size collection failed (continuing)"

# ── Step 5: Generate charts ───────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 5: Generating charts (I/O-bound)"
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
