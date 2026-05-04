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
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(xs, vals, color=COLORS, edgecolor="white", linewidth=0.5)
    ax.bar_label(bars, fmt="%.2f MB", padding=3, fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Size (MB)")
    ax.set_title("OCI image size", fontweight="bold")
    fig.tight_layout()
    out_path = out_dir / "image_size.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  Saved chart → {out_path}")


def plot_throughput(summaries: dict[str, dict], out_dir: Path) -> None:
    rps_vals = [
        (_k6_metric(summaries[v], "http_reqs", "rate") or 0.0) if v in summaries else 0.0
        for v in ORDERED_VARIANTS
    ]
    xs = np.arange(len(ORDERED_VARIANTS))
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(xs, rps_vals, color=COLORS, edgecolor="white", linewidth=0.5)
    ax.bar_label(bars, fmt="%.0f rps", padding=3, fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Throughput (rps)")
    ax.set_title("Throughput (rps)", fontweight="bold")
    fig.tight_layout()
    out_path = out_dir / "throughput.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  Saved chart → {out_path}")


def plot_latency(summaries: dict[str, dict], out_dir: Path) -> None:
    metrics = [("p50", "med"), ("p95", "p(95)"), ("p99", "p(99)")]
    x = np.arange(len(ORDERED_VARIANTS))
    width = 0.25
    fig, ax = plt.subplots(figsize=(8, 5))
    for i, (label, k6_stat) in enumerate(metrics):
        vals = [
            (_k6_metric(summaries[v], "http_req_duration", k6_stat) or 0.0) if v in summaries else 0.0
            for v in ORDERED_VARIANTS
        ]
        bars = ax.bar(x + (i - 1) * width, vals, width,
                      label=label, alpha=0.85,
                      color=["#555", "#888", "#aaa"][i])
        for bar, val in zip(bars, vals):
            if val:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.5,
                        f"{val:.0f} ms", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Latency – p50 / p95 / p99", fontweight="bold")
    ax.legend(title="Percentile")
    fig.tight_layout()
    out_path = out_dir / "latency.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  Saved chart → {out_path}")


def plot_error_rate(summaries: dict[str, dict], out_dir: Path) -> None:
    rates = [
        (_k6_metric(summaries[v], "http_req_failed", "rate") or 0.0) * 100
        if v in summaries else 0.0
        for v in ORDERED_VARIANTS
    ]
    xs = np.arange(len(ORDERED_VARIANTS))
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(xs, rates, color=COLORS, edgecolor="white", linewidth=0.5)
    ax.bar_label(bars, fmt="%.2f%%", padding=3, fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Error rate (%)")
    ax.set_title("Error rate", fontweight="bold")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    fig.tight_layout()
    out_path = out_dir / "error_rate.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  Saved chart → {out_path}")


def plot_cold_start(cold_data: list, out_dir: Path) -> None:
    by_variant = {e["variant"]: e for e in cold_data}
    means, errors = [], []
    for v in ORDERED_VARIANTS:
        entry = by_variant.get(v)
        st = entry.get("stats") if entry else None
        if st:
            means.append(st.get("mean_ms", 0.0) or 0.0)
            errors.append(st.get("stdev_ms", 0.0) or 0.0)
        else:
            means.append(0.0)
            errors.append(0.0)
    xs = np.arange(len(ORDERED_VARIANTS))
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(xs, means, yerr=errors, color=COLORS, width=0.55,
           capsize=5, edgecolor="white", linewidth=0.8)
    for x, m in zip(xs, means):
        ax.text(x, m + 5, f"{m:.0f} ms", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Time to first response (ms)")
    ax.set_title("Cold-start latency (mean ± stdev)", fontweight="bold")
    fig.tight_layout()
    out_path = out_dir / "cold_start.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  Saved chart → {out_path}")


def plot_warm_start(warm_data: list, out_dir: Path) -> None:
    by_variant = {e["variant"]: e for e in warm_data}
    means, errors = [], []
    for v in ORDERED_VARIANTS:
        entry = by_variant.get(v)
        st = entry.get("stats") if entry else None
        if st:
            means.append(st.get("mean_ms", 0.0) or 0.0)
            errors.append(st.get("stdev_ms", 0.0) or 0.0)
        else:
            means.append(0.0)
            errors.append(0.0)
    xs = np.arange(len(ORDERED_VARIANTS))
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(xs, means, yerr=errors, color=COLORS, width=0.55,
           capsize=5, edgecolor="white", linewidth=0.8)
    for x, m in zip(xs, means):
        ax.text(x, m + 5, f"{m:.0f} ms", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Time to first response (ms)")
    ax.set_title("Warm-start latency (mean ± stdev)", fontweight="bold")
    fig.tight_layout()
    out_path = out_dir / "warm_start.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  Saved chart → {out_path}")


def plot_memory(resource_data: list, out_dir: Path) -> None:
    by_variant = {e["variant"]: e for e in resource_data}
    idle  = [by_variant[v]["memory_idle_mb"]  if v in by_variant else None for v in ORDERED_VARIANTS]
    peak  = [by_variant[v]["memory_peak_mb"]  if v in by_variant else None for v in ORDERED_VARIANTS]
    x = np.arange(len(ORDERED_VARIANTS))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 5))
    bars_idle = ax.bar(x - width/2, [v or 0 for v in idle], width,
                       label="Idle", color=COLORS, alpha=0.7, edgecolor="white")
    bars_peak = ax.bar(x + width/2, [v or 0 for v in peak], width,
                       label="Peak (load)", color=COLORS, alpha=1.0, edgecolor="white",
                       hatch="//")
    for bar, val in list(zip(bars_idle, idle)) + list(zip(bars_peak, peak)):
        if val:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.3,
                    f"{val:.1f} MB", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Memory (MB)")
    ax.set_title("Memory footprint – idle vs peak", fontweight="bold")
    ax.legend(title="Phase", fontsize=9)
    fig.tight_layout()
    out_path = out_dir / "memory.png"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  Saved chart → {out_path}")


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


if __name__ == "__main__":
    main()
