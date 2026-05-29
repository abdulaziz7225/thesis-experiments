# Output structure

Every `run_experiment.sh` writes its output under `results/<example>/`.
The layout is identical across all four experiments (with one extra
panel for 04 — see below).

```text
results/<example>/
├── limited/                          # k6 + chart output for limited-thread pass
│   ├── <variant>_summary.json        # k6 aggregated metrics (rate, percentiles, etc.)
│   ├── <variant>_k6.json             # k6 time-series (line-delimited JSON)
│   └── charts/                       # PNGs from analyze.py --mode limited
├── unlimited/                        # only if --scaling-experiment unlimited|both
│   ├── <variant>_summary.json
│   ├── <variant>_k6.json
│   └── charts/
├── cold_start.json                   # [{variant, runs_ms, stats}] (run 1)
├── warm_start.json                   # [{variant, runs_ms, stats}] (runs 2-N)
├── resource_metrics.json             # [{variant, memory_idle_mb, memory_peak_mb, cpu_avg_mcores}]
├── image_sizes.json                  # {variant: MB} — full OCI image
└── binary_sizes.json                 # {variant: MB} — raw .wasm / scratch binary
```

## Chart panels per experiment

Each `analyze.py` renders one PNG per panel into
`results/<example>/<mode>/charts/`:

| File                            | Content                                         |
| ------------------------------- | ----------------------------------------------- |
| `image_size.png`                | Full OCI image size per variant                 |
| `binary_size.png`               | Raw artefact size per variant                   |
| `throughput.png`                | k6 RPS per variant                              |
| `latency.png`                   | p50 / p95 / p99 latency, grouped bars           |
| `error_rate.png`                | HTTP failure rate                               |
| `cold_start.png`                | First scale-0→1 time per variant (mean ± stdev) |
| `warm_start.png`                | Subsequent scale-0→1 times (mean ± stdev)       |
| `memory.png`                    | Idle vs peak `container_memory_rss`             |
| `cpu.png` _(01 only)_           | Avg CPU millicores during load                  |
| `rps_over_time.png` _(01 only)_ | Throughput time-series per variant              |
| `n_sweep.png` _(04 only)_       | Throughput vs request-array length (log-x)      |

## Regenerate charts without re-running

The orchestrators call `analyze.py` at the end of each run, but you can
re-render any time without re-running k6 or the cluster:

```bash
python3 benchmarks/01-prime-sieve/analyze.py     --mode limited
python3 benchmarks/01-prime-sieve/analyze.py     --mode unlimited

python3 benchmarks/02-memory-bandwidth/analyze.py --mode limited
python3 benchmarks/02-memory-bandwidth/analyze.py --mode unlimited

python3 benchmarks/03-http-fanout/analyze.py      --mode limited
python3 benchmarks/03-http-fanout/analyze.py      --mode unlimited

python3 benchmarks/04-json-roundtrip/analyze.py   --mode limited
python3 benchmarks/04-json-roundtrip/analyze.py   --mode unlimited
```
