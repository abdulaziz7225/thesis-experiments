# Notes on metric semantics

Short reference for what the chart panels actually measure and why some
results look counter-intuitive at first glance. Reads alongside the four
`BENCHMARK-NN-*.md` files. Numbers quoted below are from the existing
01-prime-sieve and 02-memory-bandwidth result snapshots; concrete values
may shift slightly after each re-run.

## 1. What `container_memory_rss` measures, and why wasm > docker

The memory chart panels (`memory.png`, idle vs peak under load) are sourced from
the Prometheus query

```promql
container_memory_rss{namespace="<example>", container="<container-name>"}
```

against cAdvisor — the kubelet's per-pod resource scraper. This is the **Linux
kernel's RSS** for the entire pod's cgroup: every resident page mapped by any
process running inside the pod, anonymous and file-backed.

**What it includes (universal)**: text segment (code), data segment, heap,
stack, runtime allocations, and any memory-mapped files the process opened.

**Docker variants — what's actually in there**: just the stripped native binary
(text + data, single-digit MB) plus the language runtime (Tokio reactor +
Hyper for Rust; Go runtime + GC arena for Go) plus per-request heap
allocations. Idle RSS in the 01/02 snapshots is **~14 MB for `docker-rust`**
and **~1 MB for `docker-golang`** — Go's GC has not yet expanded its arena at
idle, so RSS is dominated by the very small statically-linked binary.

**Spin variants — what's actually in there**: the entire
`containerd-shim-spin-v2` process tree. This shim is itself a substantial Rust
binary that statically links the **Wasmtime** runtime and the **Cranelift**
JIT compiler. On top of that the wasm component gets its **linear memory**
(allocated up-front; the default address space is wide enough for tens of MB
even when only a fraction is touched) and Cranelift's **JIT code cache** for
the compiled wasm functions. The ~200 KB `.wasm` file is a small leaf of a
much larger tree. Idle RSS in the 01/02 snapshots is **~16–20 MB** rising to
a **peak of ~85–92 MB under load**.

**Why wasm > docker even with a 10× smaller `.wasm` artifact**: the artifact
is just the program. The runtime that hosts it (Wasmtime + Cranelift + the
linear-memory arena) is shipped _separately_ in the shim and counts toward
the same cgroup. A Docker variant ships the program _as_ the runtime — when
you tear off the binary there is nothing else. So "wasm-rust uses 86 MB
peak" really means "10–15 MB of Wasmtime + the JIT cache + linear memory +
the workload's own heap". This is precisely the architectural trade-off the
thesis explores: small portable artifact, larger steady-state run-time
footprint.

**What it does not measure**: image-pull bytes (those are disk reads outside
the cgroup), network I/O, anything in another pod, anything in the kernel
that is not charged to the container's cgroup.

## 2. Concurrency model per variant — limited vs unlimited

| Variant         | Limited mode (1 thread / 1 replica, `cpu: 500m`)                                                                                                          | Unlimited mode (4 threads / 4 replicas, `cpu: 4000m`)                                                                                                 |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docker-rust`   | `TOKIO_WORKER_THREADS=1` — tokio multiplexes many concurrent requests on a single OS thread via async I/O; only one CPU-bound future progresses at a time | `TOKIO_WORKER_THREADS=4` — four worker threads, so four CPU-bound futures can progress simultaneously across four cores                               |
| `docker-golang` | `GOMAXPROCS=1` — goroutines are cooperatively scheduled onto one OS thread                                                                                | `GOMAXPROCS=4` — up to four goroutines run truly in parallel                                                                                          |
| `wasm-rust`     | SpinApp `replicas: 1` — one pod, the WASI P2 component is single-threaded _by spec_; concurrent inbound requests queue at the shim                        | SpinApp `replicas: 4` — four independent Spin pods behind one ClusterIP, each still single-threaded; the Kubernetes Service round-robins between them |
| `wasm-tinygo`   | SpinApp `replicas: 1` — one pod; TinyGo's Asyncify scheduler runs goroutines cooperatively on a single wasm thread                                        | SpinApp `replicas: 4` — four pods, each still single-threaded internally                                                                              |

So all four variants do exercise real concurrency in unlimited mode, but the
_shape_ differs sharply: Docker variants get more OS threads inside a single
process; Spin variants get more pods, each with one wasm thread.

## 3. Why unlimited mode is not 3–4× faster than limited mode

The unlimited / limited speedup is bounded well below the naïve "4× the
cores → 4× the throughput" expectation for our workloads. The bottlenecks
that come into play:

1. **Single-request workloads are largely serial.** The sieve, the SHA-256
   hash, and the JSON parse + sort are each sequential algorithms. A fourth
   worker thread does nothing for an individual request — it can only help
   when many independent requests are in flight concurrently.
2. **k6's 50 VUs cap the in-flight count.** Under our default load profile
   the bottleneck is the 50 simultaneous client connections, not server-side
   parallelism. A handler completing in 5 ms can serve ~10 000 RPS at the
   theoretical 50-VU ceiling regardless of whether the server has 1 or 4
   workers.
3. **HTTP/network stack overhead is not parallelised.** TCP accept, HTTP
   framing, and JSON serialisation all run per-request regardless of worker
   count. For our short handlers (01 sieve ≈ 1–2 ms, 02 membw ≈ 0.3 ms),
   HTTP overhead is a large fraction of total per-request time.
4. **Spin replicas route through K8s round-robin.** Four `wasm-rust` pods
   don't automatically deliver 4× throughput — the kube-proxy iptables /
   IPVS routing has its own serialisation cost, and per-pod cold state
   (wasm instance creation, Cranelift JIT warm-up) is paid by some
   requests.
5. **`limits.cpu: 4000m` is a ceiling, not a guarantee.** The Hetzner ccx23
   has 4 vCPU total, shared with kube-apiserver, etcd, kubelet,
   SpinOperator, and Prometheus. Under heavy load the variants compete with
   control-plane components for the same cores.
6. **For 03 (I/O-bound), the variant is not the bottleneck.** Each
   fan-out request waits on outbound HTTP — adding more workers on the
   fan-out side does not make `io-echo` respond any faster. The right
   scaling knob for 03 is `io-echo` replicas, not variant replicas.

Together these factors typically bound the unlimited/limited speedup to
**~1.3×–2× for our workloads**, with the higher end reached only when the
workload is CPU-saturating per request and the HTTP overhead is small
relative to compute time.

## 4. `binary_sizes.json` vs `image_sizes.json`

The two chart panels `binary_size.png` and `image_size.png` look similar but
measure different things:

- **`binary_sizes.json`** — the raw compiled artifact size: the `.wasm` file
  for the two Spin variants, the stripped scratch binary for the two Docker
  variants. Isolated from the container packaging overhead.
- **`image_sizes.json`** — the full OCI image size: the Spin OCI artifact
  (`.wasm` + Spin manifest layer) for the Spin variants, the scratch image
  (binary + `ca-certificates.crt` + image metadata) for the Docker variants.

For our scratch-based Docker images, OCI ≈ binary + ~100 KB (the cert bundle

- image metadata). For Spin images, OCI ≈ `.wasm` + a small Spin manifest
  layer. The asymmetry is small in absolute terms but the two metrics together
  make the comparison apples-to-apples: `binary_size` answers "how big is the
  compiled code?" and `image_size` answers "how big is what gets stored in the
  registry?".
