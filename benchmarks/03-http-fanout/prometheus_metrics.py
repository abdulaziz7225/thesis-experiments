"""
Collect resource metrics from Prometheus for a single variant during the
03-http-fanout (I/O-bound) experiment.

Usage:
  export THESIS_NODE_IP=<server-ip>

  python prometheus_metrics.py \
      --variant wasm-rust \
      --start 1700000000 \
      --end   1700000060

  python prometheus_metrics.py --variant wasm-rust --idle-only

Output: results/03-http-fanout/resource_metrics.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from shared.utils import (
    VARIANT_LABELS,
    VARIANTS,
    prometheus_query,
    prometheus_query_range,
    save_json,
    load_json,
)

NAMESPACE = "http-fanout"
RESULTS_SUBDIR = "03-http-fanout"

CONTAINER_PATTERNS: dict[str, str] = {
    "wasm-rust":     "http-fanout-wasm-rust",
    "wasm-tinygo":   "http-fanout-wasm-tinygo",
    "docker-rust":   "http-fanout-docker-rust",
    "docker-golang": "http-fanout-docker-golang",
}


def _first_value(results: list, default: float | None = None) -> float | None:
    if not results:
        return default
    try:
        return float(results[0]["value"][1])
    except (KeyError, IndexError, ValueError):
        return default


def _max_over_series(results: list) -> float | None:
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


def collect_idle_memory(variant: str, container: str) -> float | None:
    q = (
        f'container_memory_rss{{namespace="{NAMESPACE}",'
        f'container="{container}"}}'
    )
    r = prometheus_query(q)
    v = _first_value(r)
    return round(v / 1_048_576, 2) if v is not None else None


def collect_peak_memory(variant: str, container: str, start: float, end: float) -> float | None:
    q = (
        f'container_memory_rss{{namespace="{NAMESPACE}",'
        f'container="{container}"}}'
    )
    r = prometheus_query_range(q, start, end)
    v = _max_over_series(r)
    return round(v / 1_048_576, 2) if v is not None else None


def collect_avg_cpu(variant: str, container: str, start: float, end: float) -> float | None:
    q = (
        f'rate(container_cpu_usage_seconds_total{{namespace="{NAMESPACE}",'
        f'container="{container}"}}[30s])'
    )
    r = prometheus_query_range(q, start, end)
    all_vals: list[float] = []
    for series in r:
        for _ts, val_str in series.get("values", []):
            try:
                all_vals.append(float(val_str))
            except ValueError:
                pass
    if not all_vals:
        return None
    return round(sum(all_vals) / len(all_vals) * 1000, 1)  # millicores


def _load_existing() -> list[dict]:
    try:
        data = load_json("resource_metrics.json", subdir=RESULTS_SUBDIR)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []


def _upsert(existing: list[dict], entry: dict) -> list[dict]:
    updated = [e for e in existing if e.get("variant") != entry["variant"]]
    updated.append(entry)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Prometheus resource metrics (03-http-fanout, I/O-bound)")
    parser.add_argument("--variant", required=True, choices=list(VARIANTS.keys()))
    parser.add_argument("--start",   type=float, help="Load test start Unix timestamp")
    parser.add_argument("--end",     type=float, help="Load test end Unix timestamp")
    parser.add_argument("--idle-only", action="store_true",
                        help="Collect only idle memory (no load window required)")
    args = parser.parse_args()

    variant   = args.variant
    container = CONTAINER_PATTERNS[variant]

    if not args.idle_only and (args.start is None or args.end is None):
        parser.error("Provide --start and --end (Unix timestamps) or use --idle-only")

    print(f"Collecting Prometheus metrics for {variant} (namespace: {NAMESPACE}) …")

    entry: dict = {
        "variant":         variant,
        "label":           VARIANT_LABELS[variant],
        "memory_idle_mb":  None,
        "memory_peak_mb":  None,
        "cpu_avg_mcores":  None,
    }

    entry["memory_idle_mb"] = collect_idle_memory(variant, container)
    print(f"  idle RSS: {entry['memory_idle_mb']} MB")

    if not args.idle_only:
        entry["memory_peak_mb"] = collect_peak_memory(variant, container, args.start, args.end)
        entry["cpu_avg_mcores"] = collect_avg_cpu(variant, container, args.start, args.end)
        print(f"  peak RSS: {entry['memory_peak_mb']} MB")
        print(f"  avg CPU:  {entry['cpu_avg_mcores']} mcores")

    existing = _load_existing()
    updated  = _upsert(existing, entry)
    save_json(updated, "resource_metrics.json", subdir=RESULTS_SUBDIR)
    print(f"Saved → results/{RESULTS_SUBDIR}/resource_metrics.json")


if __name__ == "__main__":
    main()
