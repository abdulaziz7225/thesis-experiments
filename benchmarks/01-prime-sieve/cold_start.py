"""
Cold-start and warm-start measurement for 01-prime-sieve.

Terminology
-----------
cold start  – scale 0 → 1 on a node that has NOT yet pulled the image.
              In practice this is the FIRST ever scale-up on a fresh cluster
              (or after a node reimage).  Run 1 of the first invocation.

warm start  – scale 0 → 1 when the OCI image is already cached on the node
              (no image pull needed).  Subsequent runs after the image has
              been pulled are inherently warm starts.

The script distinguishes between the two using --mode:
  cold   – record only run 1 (expected to be first ever; longest due to pull)
  warm   – record runs 2-N (image cached; measures only container init + start)
  both   – record all runs; run 1 is saved to cold_start.json,
           runs 2+ to warm_start.json (DEFAULT)

Usage:
  export THESIS_NODE_IP=<server-ip>
  export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml

  # Measure both cold and warm (recommended, run once per experiment):
  python cold_start.py --runs 6 --mode both

  # Re-measure warm starts only (image already on node):
  python cold_start.py --runs 5 --mode warm

Output files (results/01-prime-sieve/):
  cold_start.json  – list of {variant, label, runs_ms, stats} (run 1 per variant)
  warm_start.json  – list of {variant, label, runs_ms, stats} (runs 2-N per variant)
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from shared.utils import (
    VARIANTS,
    VARIANT_LABELS,
    base_url,
    results_path,
    save_json,
    scale_deployment,
    wait_for_http,
    wait_for_ready,
)

NAMESPACE = "prime-sieve"

DEPLOYMENT_NAMES: dict[str, str] = {
    "wasm-rust":     "prime-sieve-wasm-rust",
    "wasm-tinygo":   "prime-sieve-wasm-tinygo",
    "docker-rust":   "prime-sieve-docker-rust",
    "docker-golang": "prime-sieve-docker-golang",
}


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
    """
    Perform `runs` scale-0→1 cycles for the given variant.

    Returns (cold_entry, warm_entry) where each is a result dict or None
    depending on mode.
    """
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
        scale_deployment(deployment, NAMESPACE, 0)
        time.sleep(3)  # give kubelet time to remove the pod

        scale_deployment(deployment, NAMESPACE, 1)

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
    parser = argparse.ArgumentParser(description="Cold/warm-start benchmark")
    parser.add_argument(
        "--runs", type=int, default=6,
        help=(
            "Total scale cycles per variant (default: 6). "
            "mode=both: run 1 → cold, runs 2-N → warm. "
            "mode=cold: only run 1. "
            "mode=warm: all runs counted as warm."
        ),
    )
    parser.add_argument(
        "--variant", choices=list(VARIANTS.keys()),
        help="Test only this variant (default: all)",
    )
    parser.add_argument(
        "--mode", choices=["cold", "warm", "both"], default="both",
        help=(
            "cold  – record only run 1 as cold start. "
            "warm  – record all runs as warm starts (image already cached). "
            "both  – run 1 = cold, runs 2+ = warm (default)."
        ),
    )
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
        save_json(cold_results, "cold_start.json")
        print("\nCold-start results → results/01-prime-sieve/cold_start.json")

    if warm_results:
        save_json(warm_results, "warm_start.json")
        print("Warm-start results → results/01-prime-sieve/warm_start.json")


if __name__ == "__main__":
    main()
