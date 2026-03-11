"""
Analyse k6 + cold/warm-start + Prometheus results for 01-prime-sieve.
Generates a multi-panel comparison figure saved to results/01-prime-sieve/.

Expected input files (produced by run_experiment.sh):
  results/01-prime-sieve/<variant>_summary.json  – k6 --summary-export per variant
  results/01-prime-sieve/<variant>_k6.json       – k6 --out json (time-series, optional)
  results/01-prime-sieve/cold_start.json         – from cold_start.py --mode cold/both
  results/01-prime-sieve/warm_start.json         – from cold_start.py --mode warm/both
  results/01-prime-sieve/resource_metrics.json   – from prometheus_metrics.py
  results/01-prime-sieve/image_sizes.json        – from run_experiment.sh (auto or manual)

Usage:
  python analyze.py [--out results/01-prime-sieve/comparison.png]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.axes import Axes
from matplotlib.figure import Figure

sys.path.insert(0, str(Path(__file__).parents[1]))
from shared.utils import VARIANT_COLORS, VARIANT_LABELS, results_path


# ── Style ─────────────────────────────────────────────────────────────────────
sns.set_theme(style="whitegrid", font_scale=1.1)
plt.rcParams.update({"figure.dpi": 150, "savefig.bbox": "tight"})

ORDERED_VARIANTS = ["wasm-rust", "wasm-tinygo", "docker-rust", "docker-golang"]
LABELS = [VARIANT_LABELS[v] for v in ORDERED_VARIANTS]
COLORS = [VARIANT_COLORS[v] for v in ORDERED_VARIANTS]


# ── Data loaders ──────────────────────────────────────────────────────────────
def load_k6_summary(variant: str) -> dict | None:
    """
    Load a k6 --summary-export JSON file.
    Key fields used:
      metrics.http_req_duration.values.{med, p(95), p(99)}  – latency in ms
      metrics.http_reqs.values.rate                         – RPS
      metrics.http_req_failed.values.rate                   – error rate (0-1)
      metrics.server_compute_us.values.{med, p(95), p(99)}  – server compute µs
    """
    path = results_path(f"{variant}_summary.json")
    if not path.exists():
        print(f"  [warn] {path.name} not found – skipping {variant}")
        return None
    with open(path) as f:
        return json.load(f)


def _k6_metric_val(summary: dict, metric: str, stat: str) -> float | None:
    try:
        return float(summary["metrics"][metric][stat])
    except (KeyError, TypeError, ValueError):
        return None


def load_k6_timeseries(variant: str) -> pd.DataFrame | None:
    """
    Parse k6 --out json line-delimited JSON to extract RPS over time.
    Each line is a JSON object; we want type=="Point", metric=="http_reqs".
    """
    path = results_path(f"{variant}_k6.json")
    if not path.exists():
        return None
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "Point" and obj.get("metric") == "http_reqs":
                rows.append({
                    "timestamp": pd.to_datetime(obj["data"]["time"]),
                    "value":     obj["data"]["value"],
                })
    if not rows:
        return None
    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    # Resample to 1-second RPS buckets.
    return df["value"].resample("1s").sum().reset_index(name="rps")


def load_startup(filename: str) -> list[dict] | None:
    path = results_path(filename)
    if not path.exists():
        print(f"  [warn] {filename} not found – skipping panel")
        return None
    with open(path) as f:
        return json.load(f)


def load_resource_metrics() -> dict[str, dict] | None:
    path = results_path("resource_metrics.json")
    if not path.exists():
        print("  [warn] resource_metrics.json not found – skipping memory/CPU panels")
        return None
    with open(path) as f:
        entries = json.load(f)
    return {e["variant"]: e for e in entries}


def load_image_sizes() -> dict[str, float] | None:
    path = results_path("image_sizes.json")
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


# ── Generic helpers ───────────────────────────────────────────────────────────
def _bar(ax: Axes, values: list[float | None], ylabel: str, title: str,
         fmt: str = "{:.0f}") -> None:
    xs = np.arange(len(ORDERED_VARIANTS))
    bars = ax.bar(xs, [v if v is not None else 0 for v in values],
                  color=COLORS, width=0.55, edgecolor="white", linewidth=0.8)
    for bar, val in zip(bars, values):
        if val is not None:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 1.01,
                fmt.format(val),
                ha="center", va="bottom", fontsize=9,
            )
    ax.set_xticks(xs)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))


# ── Individual panels ─────────────────────────────────────────────────────────
def plot_latency(ax: Axes, summaries: dict[str, dict | None]) -> None:
    """p50 / p95 / p99 grouped bar chart from k6 summaries."""
    metrics = [("p50", "med"), ("p95", "p(95)"), ("p99", "p(99)")]
    x = np.arange(len(ORDERED_VARIANTS))
    width = 0.25

    for i, (label, k6_stat) in enumerate(metrics):
        vals: list[float] = []
        for v in ORDERED_VARIANTS:
            s = summaries.get(v)
            if s is not None:
                val = _k6_metric_val(s, "http_req_duration", k6_stat)
                vals.append(val or 0)
            else:
                vals.append(0)
        bars = ax.bar(x + (i - 1) * width, vals, width,
                      label=label, alpha=0.85,
                      color=["#555", "#888", "#aaa"][i])
        for bar, val in zip(bars, vals):
            if val:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.5,
                        f"{val:.0f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Response time (ms)")
    ax.set_title("Latency – p50 / p95 / p99", fontweight="bold")
    ax.legend(title="Percentile")


def plot_throughput(ax: Axes, summaries: dict[str, dict | None]) -> None:
    vals = [_k6_metric_val(summaries.get(v), "http_reqs", "rate")
            if summaries.get(v) is not None else None
            for v in ORDERED_VARIANTS]
    _bar(ax, vals, "Requests / second", "Throughput (RPS)", fmt="{:.1f}")


def plot_failures(ax: Axes, summaries: dict[str, dict | None]) -> None:
    vals: list[float | None] = []
    for v in ORDERED_VARIANTS:
        s = summaries.get(v)
        if s is not None:
            rate = _k6_metric_val(s, "http_req_failed", "value")
            vals.append(rate * 100 if rate is not None else None)
        else:
            vals.append(None)
    _bar(ax, vals, "Error rate (%)", "Error Rate", fmt="{:.2f}")


def plot_rps_over_time(ax: Axes,
                       ts_map: dict[str, pd.DataFrame | None]) -> None:
    for v in ORDERED_VARIANTS:
        df = ts_map.get(v)
        if df is None or df.empty:
            continue
        ax.plot(
            df["timestamp"],
            df["rps"],
            label=VARIANT_LABELS[v],
            color=VARIANT_COLORS[v],
            linewidth=1.5,
        )
    ax.set_xlabel("Time")
    ax.set_ylabel("Requests / second")
    ax.set_title("Throughput over time", fontweight="bold")
    ax.legend(fontsize=9)
    ax.xaxis.set_tick_params(rotation=30)


def _startup_panel(ax: Axes, data: list[dict], title: str, ylabel: str) -> None:
    """Shared renderer for cold_start and warm_start panels."""
    means, errors, labels, colors = [], [], [], []
    order_index = {v: i for i, v in enumerate(ORDERED_VARIANTS)}
    sorted_data = sorted(
        [e for e in data if e["variant"]
            in ORDERED_VARIANTS and e.get("stats")],
        key=lambda e: order_index[e["variant"]],
    )
    for entry in sorted_data:
        st = entry["stats"]
        means.append(st["mean_ms"])
        errors.append(st["stdev_ms"])
        labels.append(VARIANT_LABELS.get(entry["variant"], entry["variant"]))
        colors.append(VARIANT_COLORS[entry["variant"]])

    xs = np.arange(len(labels))
    ax.bar(xs, means, yerr=errors, color=colors, width=0.55,
           capsize=5, edgecolor="white", linewidth=0.8)
    for x, m in zip(xs, means):
        ax.text(x, m + 5, f"{m:.0f} ms", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")


def plot_cold_start(ax: Axes, cold_data: list[dict]) -> None:
    _startup_panel(ax, cold_data,
                   "Cold-start latency (mean ± stdev)",
                   "Time to first response (ms)")


def plot_warm_start(ax: Axes, warm_data: list[dict]) -> None:
    _startup_panel(ax, warm_data,
                   "Warm-start latency (mean ± stdev)",
                   "Time to first response (ms)")


def plot_memory(ax: Axes, resource: dict[str, dict]) -> None:
    """Grouped bar: idle vs peak memory (MB) per variant."""
    x = np.arange(len(ORDERED_VARIANTS))
    width = 0.35

    idle_vals = [resource.get(v, {}).get("memory_idle_mb")
                 for v in ORDERED_VARIANTS]
    peak_vals = [resource.get(v, {}).get("memory_peak_mb")
                 for v in ORDERED_VARIANTS]

    bars_idle = ax.bar(x - width / 2,
                       [v or 0 for v in idle_vals],
                       width, label="Idle", alpha=0.7, color=COLORS, edgecolor="white")
    bars_peak = ax.bar(x + width / 2,
                       [v or 0 for v in peak_vals],
                       width, label="Peak (load)", alpha=1.0, color=COLORS, edgecolor="white",
                       hatch="//")

    for bar, val in list(zip(bars_idle, idle_vals)) + list(zip(bars_peak, peak_vals)):
        if val:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.3,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, rotation=15, ha="right")
    ax.set_ylabel("Memory (MB)")
    ax.set_title("Memory footprint – idle vs peak", fontweight="bold")
    ax.legend(title="Phase", fontsize=9)


def plot_cpu(ax: Axes, resource: dict[str, dict]) -> None:
    """Average CPU millicores during load test."""
    vals = [resource.get(v, {}).get("cpu_avg_mcores")
            for v in ORDERED_VARIANTS]
    _bar(ax, vals, "CPU (millicores)",
         "Avg CPU during load test", fmt="{:.0f}")


def plot_image_sizes(ax: Axes, sizes: dict[str, float]) -> None:
    vals = [sizes.get(v) for v in ORDERED_VARIANTS]
    _bar(ax, vals, "Size (MB)", "OCI Image Size", fmt="{:.1f}")


# ── Main ──────────────────────────────────────────────────────────────────────
def _render_panel(panel: str, summaries: dict[str, dict | None],
                  ts_map: dict[str, pd.DataFrame | None],
                  cold_data: list[dict] | None,
                  warm_data: list[dict] | None,
                  resource: dict[str, dict] | None,
                  image_sizes: dict[str, float] | None) -> Figure:
    """Create and return a standalone single-panel figure."""
    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    if panel == "latency":
        plot_latency(ax, summaries)
    elif panel == "throughput":
        plot_throughput(ax, summaries)
    elif panel == "failures":
        plot_failures(ax, summaries)
    elif panel == "rps_time":
        plot_rps_over_time(ax, ts_map)
    elif panel == "cold_start":
        assert cold_data is not None
        plot_cold_start(ax, cold_data)
    elif panel == "warm_start":
        assert warm_data is not None
        plot_warm_start(ax, warm_data)
    elif panel == "memory":
        assert resource is not None
        plot_memory(ax, resource)
    elif panel == "cpu":
        assert resource is not None
        plot_cpu(ax, resource)
    elif panel == "image_size":
        assert image_sizes is not None
        plot_image_sizes(ax, image_sizes)
    fig.tight_layout()
    return fig


# Maps panel key → output filename (no extension).
PANEL_FILENAMES: dict[str, str] = {
    "latency":    "latency",
    "throughput": "throughput",
    "failures":   "error_rate",
    "rps_time":   "rps_over_time",
    "cold_start": "cold_start",
    "warm_start": "warm_start",
    "memory":     "memory",
    "cpu":        "cpu",
    "image_size": "image_size",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse 01-prime-sieve results")
    parser.add_argument(
        "--charts-dir",
        default=str(results_path("charts")),
        help="Directory for individual chart files (default: results/01-prime-sieve/charts/)",
    )
    args = parser.parse_args()

    summaries = {v: load_k6_summary(v) for v in ORDERED_VARIANTS}
    ts_map = {v: load_k6_timeseries(v) for v in ORDERED_VARIANTS}
    cold_data = load_startup("cold_start.json")
    warm_data = load_startup("warm_start.json")
    resource = load_resource_metrics()
    image_sizes = load_image_sizes()

    has_summaries = any(v is not None for v in summaries.values())
    has_timeseries = any(v is not None for v in ts_map.values())

    if not has_summaries and cold_data is None and warm_data is None and resource is None:
        print("No result data found. Run the experiment first.")
        sys.exit(1)

    panels: list[str] = []
    if has_summaries:
        panels += ["latency", "throughput", "failures"]
    if has_timeseries:
        panels.append("rps_time")
    if cold_data:
        panels.append("cold_start")
    if warm_data:
        panels.append("warm_start")
    if resource:
        panels += ["memory", "cpu"]
    if image_sizes:
        panels.append("image_size")

    # ── Individual chart files ─────────────────────────────────────────────────
    charts_dir = Path(args.charts_dir)
    charts_dir.mkdir(parents=True, exist_ok=True)

    for panel in panels:
        fig = _render_panel(panel, summaries, ts_map, cold_data, warm_data,
                            resource, image_sizes)
        out_path = charts_dir / f"{PANEL_FILENAMES[panel]}.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Saved chart → {out_path}")



if __name__ == "__main__":
    main()
