# WebAssembly Runtime Selection Rationale

## Thesis Context

This document records the reasoning behind the choice of **SpinKube (Wasmtime/Cranelift)**
as the primary WebAssembly runtime for the experiment comparing Docker (OCI/runc) containers
against WebAssembly workloads in a Kubernetes cluster.

The experiment deploys four primary variants of the same HTTP microservice benchmark:

| Variant | Runtime | WASI | K8s runtimeClassName |
|---|---|---|---|
| `docker-rust` | runc (native) | — | *(none — cluster default)* |
| `docker-golang` | runc (native) | — | *(none — cluster default)* |
| `wasm-rust` | Wasmtime/Cranelift (via Spin) | Preview 2 | `wasmtime-spin` |
| `wasm-tinygo` | Wasmtime/Cranelift (via Spin) | Preview 2 | `wasmtime-spin` |

Optional WasmEdge/WASI Preview 1 (P1) archive variants (`wasmedge-rust`, `wasmedge-tinygo`) are available
in `wasm/wasmedge/` and `k8s/01-prime-sieve/optional/`. Deploy them by setting
`ENABLE_WASMEDGE=true` in `thesis-infra-setup`. Their results are discussed in the
thesis as Appendix B.

---

## Evaluation Criteria

A WASM runtime was considered suitable for this thesis only if it satisfied all of the
following hard constraints:

1. **Kubernetes containerd shim**: must integrate with Kubernetes via a RuntimeClass and a
   `containerd-shim-*` binary so that WASM pods are deployed identically to Docker pods
   from the Kubernetes control plane's perspective.
2. **Functional HTTP handling**: the WASM module must serve HTTP requests. The execution
   model (persistent server vs. request-handler) is an experiment variable, not a disqualifier,
   provided the framework overhead is isolated and documented.
3. **Rust support**: must execute a Rust binary compiled to a WASM target with functional
   HTTP serving.
4. **TinyGo support**: must execute a TinyGo-compiled binary with functional HTTP serving,
   enabling a Go-family language comparison with the `docker-golang` baseline.
5. **Sufficient community and maintenance**: must be actively maintained and credible enough
   for academic citation.

---

## Runtimes Evaluated

### 1. WasmEdge

- **Maintainer**: Second State (VC-backed); CNCF Sandbox project since 2021
- **Repository**: github.com/WasmEdge/WasmEdge
- **Stars / Contributors**: ~10,500 stars / 215+ contributors (as of early 2026)
- **Latest release**: v0.16.1 (January 2026); active monthly release cadence
- **Corporate backing**: Second State, Microsoft (Docker shim contributions)
- **Kubernetes shim**: `io.containerd.wasmedge.v1` — part of the containerd/runwasi project
- **WASI P1**: Full support, including a proprietary POSIX-socket extension
  (`sock_accept`, `sock_listen`, `sock_bind`, etc.) introduced in WasmEdge v0.8.2. This
  extension enables `std::net::TcpListener` in Rust and `net/http` in TinyGo to function
  inside a WASM module via a WasmEdge-specific ABI.
- **WASI Preview 2 (P2)**: Incomplete. The Component Model parser exists but the validator and
  executor are still being implemented (GitHub issue #4236, active as of early 2026).
  `wasm32-wasip2` modules cannot run on WasmEdge in production.

**Assessment**: WasmEdge satisfies all five constraints for WASI P1, but its WASI P2 gap
and proprietary socket ABI make it the legacy path rather than the current ecosystem
direction. It is retained as an optional reference comparison (Appendix B).

---

### 2. Wasmtime

- **Maintainer**: Bytecode Alliance (non-profit); primary contributors: Fastly, Intel,
  Mozilla, Microsoft, Arm, Google, Shopify
- **Repository**: github.com/bytecodealliance/wasmtime
- **Stars / Contributors**: ~17,700 stars / 672 contributors (largest community of all
  evaluated runtimes)
- **Latest release**: v42.0.1 (February 2026); monthly major releases
- **Corporate backing**: Bytecode Alliance member organisations (neutral non-profit)
- **Kubernetes shim**: `io.containerd.wasmtime.v1` — part of containerd/runwasi
- **WASI P1**: Full support
- **WASI P2**: Full support — Wasmtime is the **reference implementation** of
  WASI 0.2. Includes production-ready `wasi:sockets/tcp@0.2.0` and `wasi:http/proxy@0.2.0`.

**Role in this thesis**: Wasmtime is the JIT engine embedded inside Fermyon Spin. When this
thesis deploys SpinKube, it is deploying Wasmtime/Cranelift directly — Spin is the WASI
framework layer on top of it. Wasmtime's Bytecode Alliance governance model (neutral non-profit,
broad corporate membership) provides strong academic credibility for the chosen runtime stack.

---

### 3. Wasmer

- **Maintainer**: Wasmer Inc. (commercial company)
- **Repository**: github.com/wasmerio/wasmer
- **Stars / Contributors**: ~20,500 stars (highest of all runtimes)
- **Corporate backing**: Wasmer Inc. (VC-backed)
- **WASI P2**: Partial — Wasmer's primary differentiator is **WASIX**, a proprietary
  POSIX superset outside of the WASI standard. WASIX is not portable to Wasmtime or WasmEdge.

**Why not chosen**:

1. **Proprietary lock-in**: WASIX is a Wasmer Inc. invention not endorsed by the Bytecode
   Alliance or the W3C WebAssembly Working Group. Results on WASIX are not portable.
2. **Commercial conflict of interest**: Wasmer's primary incentive is Wasmer Cloud adoption.
   Academic benchmarks should prefer runtimes governed by neutral bodies.

---

### 4. WAMR (WebAssembly Micro Runtime)

- **Maintainer**: Bytecode Alliance; primary contributor: Intel
- **Repository**: github.com/bytecodealliance/wasm-micro-runtime
- **Kubernetes shim**: **None** — GitHub issue #337 to add WAMR to containerd/runwasi is
  open and unmerged as of early 2026.
- **Design target**: IoT, embedded systems, Trusted Execution Environments.

**Why not chosen**: The absence of a containerd shim is a hard disqualifier. WAMR cannot
create pod-level Kubernetes workloads comparable to Docker containers.

---

### 5. wazero

- **Maintainer**: Tetrate
- **Repository**: github.com/tetratelabs/wazero
- **Kubernetes shim**: **None** — wazero is an embeddable Go library, not a standalone runtime.

**Why not chosen**: wazero is architecturally incompatible — it is a library embedded inside
Go applications. It cannot replace a pod-level container runtime in Kubernetes.

---

### 6. Spin / SpinKube

- **Maintainer**: Fermyon Technologies; SpinKube donated to CNCF (Sandbox, January 2025)
- **Repository**: github.com/spinframework/spin + github.com/spinkube
- **Corporate backing**: Fermyon, Microsoft, SUSE, Liquid Reply
- **Underlying runtime**: **Wasmtime (Cranelift JIT)** — NOT WasmEdge.
  This is a critical distinction: Spin embeds Wasmtime directly. When comparing SpinKube vs.
  the optional WasmEdge variants, two variables change simultaneously: WASI version and JIT
  backend. Both are documented as confounding variables in the thesis.
- **Kubernetes shim**: `io.containerd.spin.v2` — `containerd-shim-spin-v2` implements the
  containerd shim v2 protocol and embeds Spin (which embeds Wasmtime). The SpinOperator
  (CNCF Sandbox) manages Spin workloads via the `SpinApp` CRD.
- **WASI P2**: Full support via Wasmtime; `wasi:http/incoming-handler@0.2.0`

**Execution model**: Spin uses the `wasi:http/incoming-handler` model — Spin owns the TCP
listener and HTTP parsing; for each incoming request it calls the component's `handle` export.
This is the standardised WASI P2 HTTP interface; every mature WASI P2 HTTP framework uses it.

**Why SpinKube is the primary choice**:

1. **WASI P2 is the current ecosystem direction** — `wasi:http/incoming-handler` is the
   standardised interface in WASI 0.2. The P1 socket workarounds (WasmEdge-specific ABI,
   `wasmedge_wasi_socket` crate, `//go:wasmimport` socket calls) are legacy paths that no
   longer reflect the production WASM ecosystem. The thesis should benchmark the current state.

2. **Standard library support** — With SpinKube:
   - Rust: `#[http_component]` macro via `spin-sdk = "3"` targeting `wasm32-wasip2`. No custom TCP loop.
   - TinyGo: `spinhttp.Handle()` via `github.com/spinframework/spin-go-sdk/v2` targeting `wasip1`.
     **No `server.go`, no `serveWasmEdge()`, no `//go:wasmimport` socket wiring.** TinyGo's
     `wasip2` target hardwires the `wasi:cli/command` world and cannot export
     `wasi:http/incoming-handler`; the Spin Go SDK's CGo layer exports `fermyon:spin/inbound-http`
     instead, which Spin accepts as a valid HTTP trigger interface.

3. **Bytecode Alliance runtime** — Wasmtime (inside Spin) is the Bytecode Alliance reference
   implementation of WASI 0.2, with the broadest community and most rigorous standards
   compliance. This provides stronger academic credibility than WasmEdge's proprietary ABI.

4. **CNCF Sandbox governance** — SpinKube accepted to CNCF Sandbox in January 2025; the same
   CNCF tier as WasmEdge. Both are equally citable in an academic context.

5. **`max_instances = 1` for resource fairness** — The supervisor requires that all variants
   operate within the same resource capacity. Setting `max_instances = 1` in `spin.toml` caps
   concurrent Wasm instances to 1, matching the single-thread constraint imposed on all variants
   (GOMAXPROCS=1 for docker-golang, TOKIO_WORKER_THREADS=1 for docker-rust).

---

### 7. wasmCloud

- **Maintainer**: wasmCloud project; CNCF Incubating (November 2024)
- **Underlying runtime**: Wasmtime
- **Design**: Distributed WASM application orchestration across clouds via a NATS message bus.

**Why not chosen over SpinKube**:

1. **NATS overhead** — WasmCloud routes every request through a NATS message bus, adding a
   network hop that contaminates latency measurements beyond the Wasm vs Docker question.
2. **Platform-level integration** — WasmCloud operates above Kubernetes, not at the pod level.
   SpinKube's containerd shim (`containerd-shim-spin-v2`) integrates at the same level as runc,
   making the comparison semantics directly equivalent.

---

## Summary Comparison

| Runtime | K8s shim | HTTP model | Rust wasip2 | TinyGo wasip1 (SDK) | WASI P2 | Governance | Verdict |
|---|---|---|---|---|---|---|---|
| **Spin/SpinKube** | Yes | wasi:http handler | Yes | Yes (via Spin Go SDK) | Yes | CNCF Sandbox | **Selected (primary)** |
| WasmEdge | Yes | Persistent TCP (P1 only) | No (in progress) | No (P2) | Partial | CNCF Sandbox | Optional comparison (Appendix B) |
| Wasmtime (bare) | Yes | N/A | Yes | No (P1 gap) | Yes | Bytecode Alliance | Embedded in Spin |
| Wasmer | Yes | WASIX | Yes | No | Partial | Commercial | Proprietary lock-in |
| WAMR | No | — | Limited | No | Partial | Bytecode Alliance | No K8s shim |
| wazero | No | — | N/A | N/A | In progress | Tetrate | Embedded lib only |
| wasmCloud | No (platform) | NATS-routed | Yes | Yes | Yes | CNCF Incubating | NATS overhead |

---

## Decision: SpinKube/Wasmtime (WASI P2)

SpinKube (Wasmtime/Cranelift as JIT, WASI P2) is chosen as the primary WebAssembly
runtime for the following reasons:

1. **It is the current production-ready WASI ecosystem** — WASI P2 (`wasi:http/incoming-handler`,
   Component Model, WIT interfaces) is not experimental as of 2025/2026. SpinKube v0.4.0 and
   containerd-shim-spin v0.17.0 are stable releases deployed in production.

2. **Eliminates all WASI P1 workarounds** — No `wasmedge_wasi_socket` Rust crate, no
   `//go:wasmimport` custom socket directives, no `serveWasmEdge()` TinyGo function. Both
   the Rust and TinyGo implementations become straightforward framework code.

3. **Bytecode Alliance reference runtime** — Wasmtime (inside Spin) is the most widely
   used and best-maintained WASM runtime, governed by the neutral Bytecode Alliance.

4. **CNCF Sandbox legitimacy** — SpinKube's January 2025 CNCF Sandbox acceptance is on
   par with WasmEdge's governance tier; both are equally valid academic references.

### Why WasmEdge is Now Optional (Not Primary)

WasmEdge's WASI P1 variants are retained as Appendix B comparison material for the following
reasons:

- **Historical context**: The P1 implementation documents the ecosystem constraints that existed
  before WASI P2 matured — the `wasmedge_wasi_socket` dependency, the broken TinyGo `net/http`
  server, the single-threaded accept-loop bottleneck. These findings remain valuable for
  understanding why WASI P2 was needed.
- **Concurrency bottleneck data**: The WASI P1 results (24 RPS throughput ceiling vs Docker's
  ~500 RPS) quantify the cost of the single-threaded WasmEdge socket ABI. This provides a
  concrete before/after comparison when WASI P2 results become available.
- **Not the current state**: Benchmarking WasmEdge WASI P1 as the *primary* Wasm result would
  misrepresent the current WASM-on-Kubernetes ecosystem. A thesis written in 2025/2026 should
  benchmark the current production path.

To deploy the optional WasmEdge variants:

```bash
# In thesis-infra-setup:
ENABLE_WASMEDGE=true bash cloud-init.sh
make label-node-wasmedge
make deploy-wasmedge

# In thesis-experiments:
kubectl apply -f k8s/01-prime-sieve/optional/wasm-rust.yaml
kubectl apply -f k8s/01-prime-sieve/optional/wasm-tinygo.yaml
```

---

## WASI P1 vs WASI P2: Practical Difference for This Experiment

| Aspect | WASI P1 (WasmEdge) | WASI P2 (SpinKube) |
|---|---|---|
| Binary format | Core WebAssembly module | Component Model (different binary format) |
| Sockets | WasmEdge proprietary extension | `wasi:sockets/tcp@0.2.0` (standardised) |
| HTTP | Not in spec (raw TCP loop) | `wasi:http/incoming-handler@0.2.0` |
| Portability | WasmEdge-only | Wasmtime, Spin, all WASI P2 runtimes |
| Rust target | `wasm32-wasip1` | `wasm32-wasip2` (Rust Tier 2 since v1.82) |
| TinyGo target | `-target=wasip1` + WasmEdge ABI | `-target=wasip1` + Spin Go SDK (wasip2 hardwires cli:command world) |
| K8s deployment | crun v1.22 + libwasmedge.so (optional) | containerd-shim-spin v0.17.0 (primary) |
| JIT backend | WasmEdge / LLVM | Wasmtime / Cranelift |
| Experiment role | Optional (Appendix B) | **Primary comparison** |

---

## References

- [SpinKube CNCF Sandbox](https://www.spinkube.dev/)
- [Wasmtime (Bytecode Alliance)](https://github.com/bytecodealliance/wasmtime)
- [Fermyon Spin SDK (Rust)](https://github.com/spinframework/spin-rust-sdk)
- [Fermyon Spin SDK (Go)](https://github.com/spinframework/spin-go-sdk)
- [WASI 0.2 Launch — Bytecode Alliance](https://bytecodealliance.org/articles/WASI-0.2)
- [Rust wasm32-wasip2 Tier 2 announcement](https://blog.rust-lang.org/2024/11/26/wasip2-tier-2.html)
- [SpinKube / spin-operator](https://github.com/spinkube/spin-operator)
- [containerd-shim-spin](https://github.com/spinframework/containerd-shim-spin)
- [WasmEdge GitHub (optional reference)](https://github.com/WasmEdge/WasmEdge)
- [CNCF — WebAssembly on Kubernetes](https://www.cncf.io/blog/2024/03/12/webassembly-on-kubernetes-from-containers-to-wasm-part-01/)
- [wasmCloud CNCF Incubating](https://www.cncf.io/blog/2024/11/12/cncf-welcomes-wasmcloud-to-the-cncf-incubator/)
