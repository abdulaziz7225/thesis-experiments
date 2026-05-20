"""
Cold-start and warm-start measurement for 03-http-fanout (I/O-bound).

Same methodology as 01-prime-sieve/cold_start.py — see that file for
full documentation on cold vs. warm start terminology.

Sequential execution model:
  Before running this script, ensure that the previous example's namespace
  is torn down and 03-http-fanout is deployed:
    kubectl delete namespace prime-sieve   --ignore-not-found
    kubectl delete namespace memory-bandwidth --ignore-not-found
    kubectl apply -f k8s/03-http-fanout/

Probe endpoint is /health (no outbound call). Image-pull and component-init
costs dominate the first scale-up; subsequent scale-ups are warm.

Usage:
  export THESIS_NODE_IP=<server-ip>
  export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml

  python cold_start.py --runs 6 --mode both

Output files (results/03-http-fanout/):
  cold_start.json  – run 1 per variant
  warm_start.json  – runs 2-N per variant
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from shared.utils import (
    SPINAPP_VARIANTS,
    VARIANTS,
    VARIANT_LABELS,
    base_url,
    save_json,
    scale_any,
    wait_for_http,
    wait_for_ready,
)

NAMESPACE = "http-fanout"

DEPLOYMENT_NAMES: dict[str, str] = {
    "wasm-rust":     "http-fanout-wasm-rust",
    "wasm-tinygo":   "http-fanout-wasm-tinygo",
    "docker-rust":   "http-fanout-docker-rust",
    "docker-golang": "http-fanout-docker-golang",
}

RESULTS_SUBDIR = "03-http-fanout"


def _stats(times_s: list[float]) -> dict:
    return {
        "n":         len(times_s),
        "mean_ms":   statistics.mean(times_s)   * 1000,
        "median_ms": statistics.median(times_s) * 1000,
        "stdev_ms":  statistics.stdev(times_s)  * 1000 if len(times_s) > 1 else 0.0,
        "min_ms":    min(times_s) * 1000,
        "max_ms":    max(times_s) * 1000,
    }


def _make_entry(variant: str, times_s: list[float]) -> dict:
    if not times_s:
        return {"variant": variant, "label": VARIANT_LABELS[variant],
                "runs_ms": [], "stats": None}
    st = _stats(times_s)
    print(
        f"  mean={st['mean_ms']:.0f} ms  "
        f"median={st['median_ms']:.0f} ms  "
        f"min={st['min_ms']:.0f} ms  max={st['max_ms']:.0f} ms"
    )
    return {
        "variant":  variant,
        "label":    VARIANT_LABELS[variant],
        "runs_ms":  [t * 1000 for t in times_s],
        "stats":    st,
    }


def measure_variant(variant: str, runs: int, mode: str) -> tuple[dict | None, dict | None]:
    deployment = DEPLOYMENT_NAMES[variant]
    url        = base_url(variant)

    cold_times: list[float] = []
    warm_times: list[float] = []

    print(f"\n── {VARIANT_LABELS[variant]} ({variant}) ──")

    for run in range(1, runs + 1):
        is_cold_run = (run == 1 and mode in ("cold", "both"))

        print(
            f"  run {run}/{runs} "
            f"[{'cold' if is_cold_run else 'warm'}]: "
            f"scaling to 0 …",
            end=" ", flush=True,
        )
        scale_any(variant, deployment, NAMESPACE, 0)
        time.sleep(3)

        scale_any(variant, deployment, NAMESPACE, 1)

        try:
            elapsed = wait_for_http(url, path="/health", timeout=180)
            print(f"{elapsed * 1000:.0f} ms")
            if is_cold_run:
                cold_times.append(elapsed)
            else:
                warm_times.append(elapsed)
        except TimeoutError:
            print("TIMEOUT – skipping run")

        wait_for_ready(deployment, NAMESPACE)
        time.sleep(2)

    cold_entry = _make_entry(variant, cold_times) if mode in ("cold", "both") else None
    warm_entry = _make_entry(variant, warm_times) if mode in ("warm", "both") else None
    return cold_entry, warm_entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Cold/warm-start benchmark (03-http-fanout, I/O-bound)")
    parser.add_argument("--runs",    type=int, default=6)
    parser.add_argument("--variant", choices=list(VARIANTS.keys()))
    parser.add_argument("--mode",    choices=["cold", "warm", "both"], default="both")
    args = parser.parse_args()

    if args.mode == "both" and args.runs < 2:
        parser.error("--mode both requires --runs >= 2")

    targets = [args.variant] if args.variant else list(VARIANTS.keys())

    cold_results: list[dict] = []
    warm_results: list[dict] = []

    for variant in targets:
        cold_entry, warm_entry = measure_variant(variant, args.runs, args.mode)
        if cold_entry is not None:
            cold_results.append(cold_entry)
        if warm_entry is not None:
            warm_results.append(warm_entry)

    if cold_results:
        save_json(cold_results, "cold_start.json", subdir=RESULTS_SUBDIR)
        print("\nCold-start results → results/03-http-fanout/cold_start.json")

    if warm_results:
        save_json(warm_results, "warm_start.json", subdir=RESULTS_SUBDIR)
        print("Warm-start results → results/03-http-fanout/warm_start.json")


if __name__ == "__main__":
    main()
