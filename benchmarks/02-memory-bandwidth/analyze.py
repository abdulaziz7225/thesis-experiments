"""
Analyse k6 + cold/warm-start + Prometheus results for 02-memory-bandwidth.
Generates individual chart PNGs into results/02-memory-bandwidth/charts/.

Expected input files (produced by run_experiment.sh):
  results/02-memory-bandwidth/<variant>_summary.json
  results/02-memory-bandwidth/<variant>_k6.json       (optional time-series)
  results/02-memory-bandwidth/cold_start.json
  results/02-memory-bandwidth/warm_start.json
  results/02-memory-bandwidth/resource_metrics.json
  results/02-memory-bandwidth/image_sizes.json

Usage:
  python analyze.py [--out results/02-memory-bandwidth/charts/]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

sys.path.insert(0, str(Path(__file__).parents[1]))
from shared.utils import VARIANT_COLORS, VARIANT_LABELS, results_path

RESULTS_SUBDIR = "02-memory-bandwidth"
ORDERED_VARIANTS = ["wasm-rust", "wasm-tinygo", "docker-rust", "docker-golang"]
LABELS = [VARIANT_LABELS[v] for v in ORDERED_VARIANTS]
COLORS = [VARIANT_COLORS[v] for v in ORDERED_VARIANTS]

sns.set_theme(style="whitegrid", font_scale=1.1)
plt.rcParams.update({"figure.dpi": 150, "savefig.bbox": "tight"})


def _rpath(filename: str) -> Path:
    return results_path(filename, subdir=RESULTS_SUBDIR)


def load_k6_summary(variant: str, mode: str = "limited") -> dict | None:
    path = _rpath(f"{mode}/{variant}_summary.json")
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_json_safe(filename: str) -> dict | list | None:
    path = _rpath(filename)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _k6_metric(summary: dict, metric: str, stat: str, scale: float = 1.0) -> float | None:
    try:
        return float(summary["metrics"][metric][stat]) * scale
    except (KeyError, TypeError, ValueError):
        return None


def plot_image_sizes(sizes: dict, out_dir: Path) -> None:
    vals  = [sizes.get(v, 0) for v in ORDERED_VARIANTS]
    xs = np.arange(len(ORDERED_VARIANTS))
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(xs, vals, color=COLORS, edgecolor="white", linewidth=0.5)
    ax.bar_label(bars, fmt="%.2f MB", padding=3, fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Image / artifact size (MB)")
    ax.set_title("02-memory-bandwidth: OCI Artifact Size")
    fig.tight_layout()
    fig.savefig(out_dir / "image_size.png")
    plt.close(fig)
    print("  Saved image_size.png")


def plot_throughput(summaries: dict[str, dict], out_dir: Path) -> None:
    rps_vals = [
        (_k6_metric(summaries[v], "http_reqs", "rate") or 0.0) if v in summaries else 0.0
        for v in ORDERED_VARIANTS
    ]
    xs = np.arange(len(ORDERED_VARIANTS))
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(xs, rps_vals, color=COLORS, edgecolor="white", linewidth=0.5)
    ax.bar_label(bars, fmt="%.1f RPS", padding=3, fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Requests per second (RPS)")
    ax.set_title("02-memory-bandwidth: Throughput at 50 VUs")
    fig.tight_layout()
    fig.savefig(out_dir / "throughput.png")
    plt.close(fig)
    print("  Saved throughput.png")


def plot_latency(summaries: dict[str, dict], out_dir: Path) -> None:
    percentiles = ["med", "p(95)", "p(99)"]
    x = np.arange(len(ORDERED_VARIANTS))
    width = 0.25
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, pct in enumerate(percentiles):
        vals = [
            (_k6_metric(summaries[v], "http_req_duration", pct) or 0.0) if v in summaries else 0.0
            for v in ORDERED_VARIANTS
        ]
        ax.bar(x + i * width, vals, width, label=f"p{pct.replace('(','').replace(')','').replace('med','50')}",
               color=[c + "aa" for c in COLORS] if i > 0 else COLORS)
    ax.set_xticks(x + width)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("02-memory-bandwidth: End-to-end Latency Distribution")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "latency.png")
    plt.close(fig)
    print("  Saved latency.png")


def plot_error_rate(summaries: dict[str, dict], out_dir: Path) -> None:
    rates = [
        (_k6_metric(summaries[v], "http_req_failed", "rate") or 0.0) * 100
        if v in summaries else 0.0
        for v in ORDERED_VARIANTS
    ]
    xs = np.arange(len(ORDERED_VARIANTS))
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(xs, rates, color=COLORS, edgecolor="white", linewidth=0.5)
    ax.bar_label(bars, fmt="%.1f%%", padding=3, fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("HTTP failure rate (%)")
    ax.set_title("02-memory-bandwidth: Error Rate at 50 VUs")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    fig.tight_layout()
    fig.savefig(out_dir / "error_rate.png")
    plt.close(fig)
    print("  Saved error_rate.png")


def plot_cold_start(cold_data: list, out_dir: Path) -> None:
    by_variant = {e["variant"]: e for e in cold_data}
    vals = [
        by_variant[v]["runs_ms"][0] if v in by_variant and by_variant[v]["runs_ms"] else 0.0
        for v in ORDERED_VARIANTS
    ]
    xs = np.arange(len(ORDERED_VARIANTS))
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(xs, vals, color=COLORS, edgecolor="white", linewidth=0.5)
    ax.bar_label(bars, fmt="%.0f ms", padding=3, fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Cold-start latency (ms)")
    ax.set_title("02-memory-bandwidth: Cold-Start Latency (includes image pull)")
    fig.tight_layout()
    fig.savefig(out_dir / "cold_start.png")
    plt.close(fig)
    print("  Saved cold_start.png")


def plot_warm_start(warm_data: list, out_dir: Path) -> None:
    by_variant = {e["variant"]: e for e in warm_data}
    medians = [
        by_variant[v]["stats"]["median_ms"] if v in by_variant and by_variant[v]["stats"] else 0.0
        for v in ORDERED_VARIANTS
    ]
    xs = np.arange(len(ORDERED_VARIANTS))
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(xs, medians, color=COLORS, edgecolor="white", linewidth=0.5)
    ax.bar_label(bars, fmt="%.0f ms", padding=3, fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Warm-start median latency (ms)")
    ax.set_title("02-memory-bandwidth: Warm-Start Latency (median, N=5)")
    fig.tight_layout()
    fig.savefig(out_dir / "warm_start.png")
    plt.close(fig)
    print("  Saved warm_start.png")


def plot_memory(resource_data: list, out_dir: Path) -> None:
    by_variant = {e["variant"]: e for e in resource_data}
    idle  = [by_variant[v]["memory_idle_mb"]  if v in by_variant else None for v in ORDERED_VARIANTS]
    peak  = [by_variant[v]["memory_peak_mb"]  if v in by_variant else None for v in ORDERED_VARIANTS]
    x = np.arange(len(ORDERED_VARIANTS))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(x - width/2, [v or 0 for v in idle], width, label="Idle RSS", color=COLORS, alpha=0.7)
    ax.bar(x + width/2, [v or 0 for v in peak], width, label="Peak RSS", color=COLORS)
    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Memory RSS (MB)")
    ax.set_title("02-memory-bandwidth: Memory RSS (idle and peak)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "memory.png")
    plt.close(fig)
    print("  Saved memory.png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        default="limited",
        choices=["limited", "unlimited"],
        help="Scaling mode to analyse (reads from results/02-memory-bandwidth/<mode>/)",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.out is None:
        args.out = str(_rpath(f"{args.mode}/charts"))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries = {}
    for v in ORDERED_VARIANTS:
        s = load_k6_summary(v, args.mode)
        if s:
            summaries[v] = s

    sizes       = load_json_safe("image_sizes.json")   or {}
    cold_data   = load_json_safe("cold_start.json")    or []
    warm_data   = load_json_safe("warm_start.json")    or []
    resource_data = load_json_safe("resource_metrics.json") or []

    print(f"Generating charts → {out_dir}")

    if sizes:
        plot_image_sizes(sizes, out_dir)
    if summaries:
        plot_throughput(summaries, out_dir)
        plot_latency(summaries, out_dir)
        plot_error_rate(summaries, out_dir)
    if cold_data:
        plot_cold_start(cold_data, out_dir)
    if warm_data:
        plot_warm_start(warm_data, out_dir)
    if resource_data:
        plot_memory(resource_data, out_dir)

    print("Done.")


if __name__ == "__main__":
    main()
