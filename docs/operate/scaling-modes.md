# Limited vs unlimited mode

All four `run_experiment.sh` orchestrators accept
`--scaling-experiment limited|unlimited|both` (default: `limited`).

| Mode        | Docker variants                                                                    | Spin variants        | Purpose                                                                                                                                                                                                           |
| ----------- | ---------------------------------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `limited`   | `GOMAXPROCS=1`, `TOKIO_WORKER_THREADS=1`                                           | SpinApp `replicas=1` | Single-threaded baseline. Isolates the per-instance overhead of each runtime + language combination.                                                                                                              |
| `unlimited` | `GOMAXPROCS=4`, `TOKIO_WORKER_THREADS=4`                                           | SpinApp `replicas=4` | Matches the four physical vCPUs of the Hetzner ccx23 host. Exercises whatever parallelism each variant exposes (multi-threaded tokio / Go scheduler, or 4 single-threaded Spin pods round-robined by kube-proxy). |
| `both`      | runs `limited`, then `unlimited`, then restores `limited` for the cold-start phase |                      | What you want for the full chapter-6 figures.                                                                                                                                                                     |

The `limits.cpu` field in the Kubernetes manifests is set to `4000m` so
cgroup CPU bandwidth control does not throttle the additional threads
in unlimited mode. The `requests.cpu` stays at `250m` so all four wasm
replicas schedule cleanly alongside kube-system pods.

## Why unlimited is not 3-4× limited

A natural expectation is that unlimited mode (4 cores / 4 replicas)
should give ~4× the throughput of limited mode (1 core / 1 replica).
It typically does not, by a wide margin. The reasons are listed in
detail in
[../reference/notes-on-metrics.md § 3](../reference/notes-on-metrics.md) —
the short summary:

1. Single-request workloads (sieve, hash, JSON parse) are sequential —
   more workers help only with concurrent inbound requests.
2. The 50-VU load profile caps in-flight requests well below the
   server's parallel capacity for our short handlers.
3. HTTP / network stack overhead is per-request regardless of worker
   count.
4. Spin's 4 replicas route through kube-proxy round-robin, which adds
   its own serialisation cost.
5. The ccx23 has 4 vCPU total — variants compete with kube-apiserver +
   etcd + Prometheus.
6. For 03 (I/O-bound), `io-echo` is the bottleneck, not the variant.

## Results layout per mode

Each mode's k6 output goes to a separate subdirectory under
`results/<example>/`:

```text
results/<example>/
├── limited/
│   ├── <variant>_summary.json    # k6 aggregated metrics
│   ├── <variant>_k6.json         # k6 time-series (line-delimited)
│   └── charts/                   # PNGs from analyze.py --mode limited
└── unlimited/                    # only if --scaling-experiment unlimited|both
    └── charts/
```
