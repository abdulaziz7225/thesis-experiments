#!/usr/bin/env bash
# ============================================================
# run_experiment.sh – Orchestrate the full 01-prime-sieve run
# ============================================================
#
# USAGE:
#   export THESIS_NODE_IP=<hetzner-server-ip>
#   export KUBECONFIG=<path-to>/hetzner-thesis.yaml
#   ./run_experiment.sh [--users 50] [--ramp 20s] [--duration 60s] \
#                       [--limit 100000] [--cold-start-runs 6] [--no-list 1]
#
# WHAT IT DOES:
#   1. Verifies all four variants are healthy.
#   2. Runs a k6 load test against each variant sequentially.
#      After each run, queries Prometheus for memory/CPU metrics.
#   3. Runs cold-start AND warm-start measurements (--mode both).
#   4. Collects OCI image sizes via local docker inspect (falls back to manual prompt).
#   5. Calls analyze.py to generate comparison charts.
#
# OUTPUT:  results/01-prime-sieve/
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/../../results/01-prime-sieve"
mkdir -p "${RESULTS_DIR}"

# ── Defaults ──────────────────────────────────────────────────────────────────
VUS=50
RAMP="20s"
DURATION="60s"
SIEVE_LIMIT=100000
COLD_START_RUNS=6
NO_LIST=1

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --users)            VUS="$2";             shift 2 ;;
    --ramp)             RAMP="$2";            shift 2 ;;
    --duration)         DURATION="$2";        shift 2 ;;
    --limit)            SIEVE_LIMIT="$2";     shift 2 ;;
    --cold-start-runs)  COLD_START_RUNS="$2"; shift 2 ;;
    --no-list)          NO_LIST="$2";         shift 2 ;;
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

# ── Step 1: Pre-flight health check ──────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 1: Health checks"
echo "══════════════════════════════════════════"
for variant in wasm-rust wasm-tinygo docker-rust docker-golang; do
  port="${PORTS[$variant]}"
  url="http://${THESIS_NODE_IP}:${port}"
  wait_healthy "${url}" || { echo "  WARN: ${variant} is not healthy – skipping"; }
done

# ── Step 2: Load tests + Prometheus resource metrics ─────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 2: Load tests (k6)"
echo "  vus=${VUS}  duration=${DURATION}  sieve-limit=${SIEVE_LIMIT}"
echo "══════════════════════════════════════════"

for variant in wasm-rust wasm-tinygo docker-rust docker-golang; do
  port="${PORTS[$variant]}"
  url="http://${THESIS_NODE_IP}:${port}"

  echo ""
  echo "  ── ${variant} (${url}) ──"

  # Ensure the variant is healthy (it may have gone down during the previous test).
  echo "  Waiting for ${variant} to be healthy before load test …"
  wait_healthy "${url}" || echo "  WARN: ${variant} unhealthy; load test may produce no data"

  # Collect idle/baseline memory before the load test.
  echo "  Collecting baseline memory …"
  python3 "${SCRIPT_DIR}/prometheus_metrics.py" \
    --variant "${variant}" \
    --idle-only 2>&1 | sed 's/^/    /' || echo "  WARN: Prometheus query failed (continuing)"

  # Record timestamps around the k6 run.
  START_TS=$(date +%s)

  k6 run \
    --env BASE_URL="${url}" \
    --env VARIANT="${variant}" \
    --env VUS="${VUS}" \
    --env RAMP="${RAMP}" \
    --env DURATION="${DURATION}" \
    --env SIEVE_LIMIT="${SIEVE_LIMIT}" \
    --env NO_LIST="${NO_LIST}" \
    --summary-export "${RESULTS_DIR}/${variant}_summary.json" \
    --out "json=${RESULTS_DIR}/${variant}_k6.json" \
    "${SCRIPT_DIR}/k6-load-test.js" \
    2>&1 | sed 's/^/    /' || true

  END_TS=$(date +%s)

  echo "  k6 summary saved to ${RESULTS_DIR}/${variant}_summary.json"

  # Query Prometheus for peak memory and avg CPU during the load window.
  echo "  Collecting load-test resource metrics …"
  python3 "${SCRIPT_DIR}/prometheus_metrics.py" \
    --variant "${variant}" \
    --start "${START_TS}" \
    --end   "${END_TS}" \
    2>&1 | sed 's/^/    /' || echo "  WARN: Prometheus query failed (continuing)"
done

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
  # Use local `docker inspect` — images are built locally so this always works
  # without needing any SSH key or remote access.
  if command -v docker >/dev/null 2>&1; then
    echo "  Reading local image sizes via docker inspect …"
    python3 - "${IMAGE_SIZES_FILE}" <<'PYEOF'
import json, subprocess, sys

out_path = sys.argv[1]

# Full image references as used in k8s manifests (docker.io/username/image:tag).
images = {
    "docker.io/abdulaziz7225/prime-sieve-wasm-rust:latest":     "wasm-rust",
    "docker.io/abdulaziz7225/prime-sieve-wasm-tinygo:latest":   "wasm-tinygo",
    "docker.io/abdulaziz7225/prime-sieve-docker-rust:latest":   "docker-rust",
    "docker.io/abdulaziz7225/prime-sieve-docker-golang:latest": "docker-golang",
}

sizes = {}
for image, variant in images.items():
    result = subprocess.run(
        ["docker", "inspect", "--format={{.Size}}", image],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        size_bytes = int(result.stdout.strip())
        sizes[variant] = round(size_bytes / 1_048_576, 2)

if len(sizes) == 4:
    with open(out_path, "w") as f:
        json.dump(sizes, f, indent=2)
    print(f"  Saved {out_path}")
    for k, v in sizes.items():
        print(f"    {k}: {v} MB")
else:
    found = list(sizes.keys())
    missing = [v for v in images.values() if v not in sizes]
    print(f"  docker inspect found {len(sizes)}/4 images.")
    print(f"  Missing: {missing}")
    print("  Make sure you have built the images locally before running this script.")
    sys.exit(1)
PYEOF
  fi
fi

# Manual fallback if docker inspect failed or docker is not installed.
if [[ ! -f "${IMAGE_SIZES_FILE}" ]]; then
  echo ""
  echo "  Could not collect image sizes automatically."
  echo "  Run the following locally (where you built the images) and create ${IMAGE_SIZES_FILE}:"
  echo ""
  echo "  docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep prime-sieve"
  echo ""
  echo '  Then create image_sizes.json:'
  echo '  {"wasm-rust": <MB>, "wasm-tinygo": <MB>, "docker-rust": <MB>, "docker-golang": <MB>}'
  echo ""
  echo "  (Skipping auto-analysis – re-run analyze.py after creating the file.)"
fi

# ── Step 5: Generate charts ───────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 5: Generating comparison charts"
echo "══════════════════════════════════════════"

python3 "${SCRIPT_DIR}/analyze.py" --out "${RESULTS_DIR}/comparison.png" \
  2>&1 | sed 's/^/    /'

echo ""
echo "Done!  Results in ${RESULTS_DIR}/"
echo "  comparison.png           main figure"
echo "  *_summary.json           per-variant k6 summaries"
echo "  *_k6.json                per-variant k6 time-series (raw)"
echo "  cold_start.json          cold-start timings (run 1)"
echo "  warm_start.json          warm-start timings (runs 2+)"
echo "  resource_metrics.json    memory + CPU from Prometheus"
echo "  image_sizes.json         OCI image sizes"
