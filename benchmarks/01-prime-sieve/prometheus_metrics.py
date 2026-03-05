"""
Collect resource metrics from Prometheus for a single variant over a load-test window.

Usage:
  export THESIS_NODE_IP=<server-ip>

  python prometheus_metrics.py \
      --variant wasm-rust \
      --start 1700000000 \
      --end   1700000060

  # To query idle (baseline) memory only, omit --start/--end:
  python prometheus_metrics.py --variant wasm-rust --idle-only

Output: results/01-prime-sieve/resource_metrics.json
  (appended / updated per variant)

Schema per variant entry:
  {
    "variant": "wasm-rust",
    "label":   "Rust + WASM",
    "memory_idle_mb":  <float | null>,
    "memory_peak_mb":  <float | null>,
    "cpu_avg_mcores":  <float | null>   # millicores during load window
  }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from shared.utils import (
    VARIANT_LABELS,
    VARIANTS,
    prometheus_query,
    prometheus_query_range,
    results_path,
)

# Kubernetes namespace where all prime-sieve pods live.
NAMESPACE = "prime-sieve"

# Container name suffix pattern used in Prometheus labels.
# kube-prometheus-stack uses the Deployment container name directly.
CONTAINER_PATTERNS: dict[str, str] = {
    "wasm-rust":     "prime-sieve-wasm-rust",
    "wasm-tinygo":   "prime-sieve-wasm-tinygo",
    "docker-rust":   "prime-sieve-docker-rust",
    "docker-golang": "prime-sieve-docker-golang",
}


def _first_value(results: list, default: float | None = None) -> float | None:
    """Return the numeric value from the first Prometheus result series."""
    if not results:
        return default
    try:
        return float(results[0]["value"][1])
    except (KeyError, IndexError, ValueError):
        return default


def _max_over_series(results: list) -> float | None:
    """Return the maximum value seen across all data points in all series."""
    peak: float | None = None
    for series in results:
        for _ts, val_str in series.get("values", []):
            try:
                v = float(val_str)
                if peak is None or v > peak:
                    peak = v
            except ValueError:
                pass
    return peak


def _avg_over_series(results: list) -> float | None:
    """Return the mean value across all data points in all series."""
    total, count = 0.0, 0
    for series in results:
        for _ts, val_str in series.get("values", []):
            try:
                total += float(val_str)
                count += 1
            except ValueError:
                pass
    return total / count if count else None


def collect_idle_memory(container: str) -> float | None:
    """Query current (idle/baseline) memory working set in MB."""
    query = (
        f'container_memory_working_set_bytes{{'
        f'namespace="{NAMESPACE}", container="{container}"}}'
    )
    results = prometheus_query(query)
    val = _first_value(results)
    return val / 1_048_576 if val is not None else None


def collect_peak_memory(container: str, start: float, end: float) -> float | None:
    """Query peak memory working set (MB) over a time window."""
    window_s = max(int(end - start), 1)
    query = (
        f'max_over_time('
        f'container_memory_working_set_bytes{{'
        f'namespace="{NAMESPACE}", container="{container}"}}'
        f'[{window_s}s])'
    )
    results = prometheus_query_range(query, start, end, step="5s")
    val = _max_over_series(results)
    return val / 1_048_576 if val is not None else None


def collect_avg_cpu(container: str, start: float, end: float) -> float | None:
    """Query average CPU usage in millicores over a time window."""
    query = (
        f'rate(container_cpu_usage_seconds_total{{'
        f'namespace="{NAMESPACE}", container="{container}"}}'
        f'[1m]) * 1000'
    )
    results = prometheus_query_range(query, start, end, step="5s")
    return _avg_over_series(results)


def load_existing(path: Path) -> dict[str, dict]:
    """Load existing resource_metrics.json as a dict keyed by variant."""
    if path.exists():
        with open(path) as f:
            entries = json.load(f)
        return {e["variant"]: e for e in entries}
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Prometheus resource metrics")
    parser.add_argument(
        "--variant", choices=list(VARIANTS.keys()), required=True,
        help="Variant to measure",
    )
    parser.add_argument(
        "--start", type=float, default=None,
        help="Unix timestamp of load-test start (for peak memory & CPU)",
    )
    parser.add_argument(
        "--end", type=float, default=None,
        help="Unix timestamp of load-test end",
    )
    parser.add_argument(
        "--idle-only", action="store_true",
        help="Collect idle/baseline memory only (skip peak and CPU)",
    )
    args = parser.parse_args()

    variant   = args.variant
    container = CONTAINER_PATTERNS[variant]
    label     = VARIANT_LABELS[variant]

    out_path = results_path("resource_metrics.json")
    existing = load_existing(out_path)

    entry: dict = existing.get(variant, {"variant": variant, "label": label})

    print(f"\n── Resource metrics: {label} ──")

    # Always collect idle memory (point-in-time, reflects current state).
    print("  Querying idle memory …", end=" ", flush=True)
    idle_mb = collect_idle_memory(container)
    entry["memory_idle_mb"] = idle_mb
    print(f"{idle_mb:.1f} MB" if idle_mb is not None else "n/a")

    if not args.idle_only and args.start is not None and args.end is not None:
        print("  Querying peak memory during load window …", end=" ", flush=True)
        peak_mb = collect_peak_memory(container, args.start, args.end)
        entry["memory_peak_mb"] = peak_mb
        print(f"{peak_mb:.1f} MB" if peak_mb is not None else "n/a")

        print("  Querying avg CPU millicores during load window …", end=" ", flush=True)
        cpu_mc = collect_avg_cpu(container, args.start, args.end)
        entry["cpu_avg_mcores"] = cpu_mc
        print(f"{cpu_mc:.1f} m" if cpu_mc is not None else "n/a")
    else:
        entry.setdefault("memory_peak_mb", None)
        entry.setdefault("cpu_avg_mcores", None)

    existing[variant] = entry

    # Write back as a list (preserves ordering).
    ordered = ["wasm-rust", "wasm-tinygo", "docker-rust", "docker-golang"]
    out_list = [existing[v] for v in ordered if v in existing]
    # Append any variants not in the standard order.
    for v, e in existing.items():
        if v not in ordered:
            out_list.append(e)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out_list, f, indent=2)
    print(f"  Saved → {out_path}")


if __name__ == "__main__":
    main()
