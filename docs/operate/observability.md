# Observability

The `make deploy` step in
[../setup/02-infrastructure.md](../setup/02-infrastructure.md) brings up
`kube-prometheus-stack` — Prometheus, Grafana, node-exporter,
kube-state-metrics — exposed via NodePorts.

| Service    | URL                              | Credentials                |
| ---------- | -------------------------------- | -------------------------- |
| Grafana    | `http://${THESIS_NODE_IP}:32000` | `admin` / `thesis-grafana` |
| Prometheus | `http://${THESIS_NODE_IP}:32090` | —                          |

The benchmark orchestrators scrape Prometheus directly for the
`memory.png` and `cpu.png` panels — see
[run-benchmarks.md](run-benchmarks.md) step 5.

## Useful PromQL queries

```promql
# Memory RSS per variant (substitute the namespace for the active experiment)
container_memory_rss{namespace="prime-sieve"}
container_memory_rss{namespace="memory-bandwidth"}
container_memory_rss{namespace="http-fanout"}
container_memory_rss{namespace="json-roundtrip"}

# CPU usage rate (millicores)
rate(container_cpu_usage_seconds_total{namespace="prime-sieve"}[30s]) * 1000

# Pod restart count (catches OOM kills / crash loops)
kube_pod_container_status_restarts_total{namespace=~"prime-sieve|memory-bandwidth|http-fanout|json-roundtrip"}

# Node-level CPU saturation
1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))

# Node-level memory
node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes
```

## What `container_memory_rss` actually measures

The short answer is "everything inside the pod's cgroup, including the
runtime that hosts the .wasm". The long answer — and the explanation of
why wasm variants show higher RSS than Docker variants despite their
much smaller `.wasm` artefacts — is in
[../reference/notes-on-metrics.md § 1](../reference/notes-on-metrics.md).

## Grafana dashboards

`kube-prometheus-stack` ships a comprehensive set of default dashboards
under `Dashboards → Browse → General`. The most relevant for these
experiments:

- **Kubernetes / Compute Resources / Namespace (Pods)** — CPU and
  memory per pod in the active experiment namespace
- **Kubernetes / Compute Resources / Node (Pods)** — node-level
  saturation (catches the cluster-collapse scenario described in
  [../reference/troubleshooting.md](../reference/troubleshooting.md))
- **Node Exporter / Nodes** — kernel / network stats; useful for
  diagnosing conntrack table exhaustion when 03 runs at high VUs
