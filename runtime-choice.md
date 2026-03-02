# WebAssembly Runtime Selection Rationale

## Thesis Context

This document records the research and reasoning behind the choice of **WasmEdge** as the
WebAssembly runtime for the experiment comparing Docker (OCI/runc) containers against
WebAssembly workloads in a Kubernetes cluster.

The experiment deploys four variants of the same HTTP microservice benchmark:

| Variant | Runtime | K8s runtimeClassName |
|---|---|---|
| `docker/rust` | runc (default OCI) | *(none — cluster default)* |
| `docker/golang` | runc (default OCI) | *(none — cluster default)* |
| `wasm/rust` | WasmEdge via runwasi | `wasmedge` |
| `wasm/tinygo` | WasmEdge via runwasi | `wasmedge` |

All WASM pods use the OCI image annotation `module.wasm.image/variant: compat-smart`,
which instructs WasmEdge's containerd shim to auto-detect the module type and execution
mode.

---

## Evaluation Criteria

A WASM runtime was considered suitable for this thesis only if it satisfied all of the
following hard constraints:

1. **Kubernetes containerd shim**: must integrate with Kubernetes via a RuntimeClass and a
   `containerd-shim-*` binary so that WASM pods are deployed identically to Docker pods
   from the Kubernetes control plane's perspective.
2. **Long-running TCP server model**: the WASM module must own the listen/accept loop
   (equivalent to a traditional microservice). Runtimes that impose a per-request
   instantiation model (FaaS/handler style) are architecturally incomparable to
   long-running Docker containers and were therefore excluded.
3. **Rust support**: must execute a Rust binary compiled to a WASM target with functional
   TCP networking (`std::net::TcpListener`).
4. **TinyGo support**: must execute a TinyGo-compiled binary with functional `net/http`
   server behaviour.
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
- **Kubernetes shim**: `io.containerd.wasmedge.v1` — part of the containerd/runwasi
  project, shim v0.6.0 released May 2025
- **WASI Preview 1**: Full support, including a proprietary POSIX-socket extension
  (`sock_accept`, `sock_listen`, `sock_bind`, etc.) introduced in WasmEdge v0.8.2 — before
  WASI formally standardised sockets. This extension is what enables `std::net::TcpListener`
  in Rust and `net/http` in TinyGo to function inside a WASM module.
- **WASI Preview 2**: Incomplete. The Component Model parser exists but the validator and
  executor are still being implemented (GitHub issue #4236, active as of early 2026).
  `wasm32-wasip2` modules cannot run on WasmEdge in production.

**Constraint satisfaction**:

| Criterion | Satisfied? |
|---|---|
| K8s containerd shim | Yes |
| Long-running TCP server | Yes (via WasmEdge socket extension) |
| Rust wasm32-wasip1 | Yes |
| TinyGo wasip1 net/http | Yes (via WasmEdge socket extension) |
| Active maintenance | Yes |

**Assessment**: The only runtime that satisfies all five constraints simultaneously.
The proprietary socket extension is a deliberate design choice by the WasmEdge team to
make cloud-native networking possible while WASI's own sockets specification was still being
finalised. The downside is that modules using this extension are not portable to other
runtimes — a trade-off explicitly noted as a thesis finding.

---

### 2. Wasmtime

- **Maintainer**: Bytecode Alliance (non-profit); primary contributors: Fastly, Intel,
  Mozilla, Microsoft, Arm, Google, Shopify
- **Repository**: github.com/bytecodealliance/wasmtime
- **Stars / Contributors**: ~17,700 stars / 672 contributors (largest community of all
  evaluated runtimes)
- **Latest release**: v42.0.1 (February 2026); monthly major releases (Semantic
  Versioning — v1 through v42 in ~3 years)
- **Corporate backing**: Bytecode Alliance member organisations (neutral non-profit)
- **Kubernetes shim**: `io.containerd.wasmtime.v1` — part of containerd/runwasi
- **WASI Preview 1**: Full support
- **WASI Preview 2**: Full support — Wasmtime is the **reference implementation** of
  WASI 0.2. Includes production-ready `wasi:sockets/tcp@0.2.0` and `wasi:http/proxy@0.2.0`.
  `wasm32-wasip2` Rust binaries with `std::net::TcpListener` run correctly on Wasmtime 17+
  via the standardised `wasi:sockets` interface.

**Constraint satisfaction**:

| Criterion | Satisfied? |
|---|---|
| K8s containerd shim | Yes |
| Long-running TCP server (Rust wasip2) | Yes |
| Rust wasm32-wasip1 | Yes |
| TinyGo wasip1 net/http (TCP server) | No — TinyGo `net/http` server does not work on Wasmtime without WasmEdge's proprietary socket ABI |
| Active maintenance | Yes (most active of all runtimes) |

**Why not chosen**: Wasmtime does not support TinyGo's `net/http` TCP server model.
TinyGo's standard library `net` package, when targeting `wasip1`, relies on the WasmEdge
socket extension ABI. This extension is absent in Wasmtime, which implements only the
standardised WASI socket syscalls. Switching to Wasmtime would require abandoning the
TinyGo variant or rewriting it against a different networking API — eliminating one of the
two WASM languages from the comparison. The benchmark's language-agnostic coverage
(Rust and Go) was deemed more valuable than runtime standardisation.

Additionally, `wasm32-wasip2` + Wasmtime for Rust is viable but requires the Component
Model adapter toolchain (`wasm-tools`, `wit-bindgen`, `cargo-component`), which would
introduce substantial build complexity for no comparative benefit given the TinyGo
constraint.

**Wasmtime as a thesis finding**: Wasmtime's Bytecode Alliance governance model (neutral
non-profit, broad corporate membership) and its role as the WASI 0.2 reference
implementation make it the most academically credible runtime for long-term reference.
This is noted in the thesis discussion as the direction WASM microservices should evolve
toward once TinyGo's wasip2 networking story matures.

---

### 3. Wasmer

- **Maintainer**: Wasmer Inc. (commercial company)
- **Repository**: github.com/wasmerio/wasmer
- **Stars / Contributors**: ~20,500 stars (highest of all runtimes) / large fork count
- **Latest release**: v7.x (active as of early 2026)
- **Corporate backing**: Wasmer Inc. (VC-backed); revenue model via Wasmer Cloud platform
- **Kubernetes shim**: `io.containerd.wasmer.v1` — present in containerd/runwasi
- **WASI Preview 1**: Supported
- **WASI Preview 2**: Partial — Wasmer's primary differentiator is **WASIX**, a proprietary
  POSIX superset that extends WASM with full POSIX compatibility (threads, fork, sockets,
  etc.) outside of the WASI standard. WASIX is Wasmer-only; binaries using it are not
  portable to Wasmtime or WasmEdge.
- **TinyGo net/http**: Theoretically possible via WASIX socket support, but WASIX is not
  compatible with TinyGo's wasip1 socket extension ABI.

**Why not chosen**:

1. **Proprietary lock-in**: WASIX is a Wasmer Inc. invention not endorsed by the Bytecode
   Alliance or the W3C WebAssembly Working Group. Benchmarking results obtained on WASIX
   would be non-portable and would weaken the thesis's generalisability.
2. **TinyGo compatibility**: the same gap as Wasmtime — WASIX is not TinyGo's socket ABI.
3. **Commercial conflict of interest**: Wasmer's primary incentive is to drive adoption of
   Wasmer Cloud. Academic benchmarks should prefer runtimes governed by neutral bodies
   (Bytecode Alliance, CNCF) where possible.
4. **Star count misleading**: Wasmer's ~20,500 stars are partly attributable to early
   positioning as the first user-friendly WASM runtime (circa 2019) rather than current
   production adoption in the cloud-native Kubernetes ecosystem.

---

### 4. WAMR (WebAssembly Micro Runtime)

- **Maintainer**: Bytecode Alliance; primary contributor: Intel (43% of PRs); also Amazon,
  Midokura, Xiaomi, SECO
- **Repository**: github.com/bytecodealliance/wasm-micro-runtime
- **Stars / Contributors**: ~5,800 stars / 212+ contributors
- **Latest release**: WAMR-2.4.4 (November 2025); 707 PRs merged in 2024 alone
- **Corporate backing**: Intel (primary), Amazon Web Services
- **Kubernetes shim**: **None** — GitHub issue #337 to add WAMR to containerd/runwasi is
  open and unmerged as of early 2026
- **WASI Preview 1**: Full support
- **WASI Preview 2**: Partial
- **Design target**: IoT, embedded systems, Trusted Execution Environments (TEE), and
  bare-metal edge deployments. WAMR supports compilation ahead-of-time (AOT) for
  resource-constrained environments.

**Why not chosen**: The absence of a containerd shim is a hard disqualifier. Without a
Kubernetes RuntimeClass integration, WASM pods cannot be deployed via the standard
Kubernetes pod scheduling mechanism. WAMR is an excellent runtime for its intended
embedded/IoT context but is not a cloud-native Kubernetes runtime. There is no path
to make WAMR comparable to a Docker container at the pod level without a custom
containerd shim.

---

### 5. wazero

- **Maintainer**: Tetrate (CNCF ecosystem company); used by Docker Engine, Envoy proxy,
  and several Go-native projects
- **Repository**: github.com/tetratelabs/wazero
- **Stars / Contributors**: ~6,000 stars / 316+ forks / used by 5,200+ projects
- **Latest release**: v1.11.0 (December 2025)
- **Corporate backing**: Tetrate
- **Kubernetes shim**: **None** — wazero is an embeddable Go library, not a standalone
  runtime. It has no containerd shim and cannot serve as a Kubernetes RuntimeClass.
- **WASI Preview 1**: Full support (as an embedded library)
- **WASI Preview 2**: In progress (GitHub issue #2289, unresolved)

**Why not chosen**: wazero is architecturally incompatible with the thesis experiment.
It is a library that Go applications embed to execute WASM modules — it is not a
standalone container runtime. While wazero runs inside Docker Engine itself, it cannot
replace Docker Engine as the pod-level runtime in Kubernetes. There is no mechanism to
schedule a wazero-executed WASM module as a Kubernetes pod comparable to a Docker
container.

---

### 6. Spin / SpinKube

- **Maintainer**: Fermyon Technologies; SpinKube donated to CNCF (Sandbox, March 2024)
- **Repository**: github.com/spinframework/spin + github.com/spinkube
- **Stars**: Well-established across spinframework and SpinKube repositories
- **Corporate backing**: Fermyon, Microsoft, SUSE, Liquid Reply
- **Underlying runtime**: Wasmtime (Spin uses Wasmtime internally)
- **Kubernetes shim**: `io.containerd.spin.v2` — `containerd-shim-spin` (built on
  runwasi library); Spin Operator (CNCF Sandbox) provides a higher-level CRD-based
  deployment model
- **WASI Preview 2**: Full support (via Wasmtime); SpinKube was an early adopter of
  `wasi:http/proxy@0.2.0`

**Why not chosen — the execution model disqualifier**:

Spin uses the **`wasi:http/proxy` handler model**: the runtime (Spin) owns the TCP
listener and HTTP parsing layer. For each incoming HTTP request, Spin instantiates a
fresh WASM component, calls its `handle` export, and discards the instance after the
response. This is architecturally equivalent to CGI (Common Gateway Interface) or
AWS Lambda — a new process per request.

Docker containers, by contrast, run as **persistent long-running processes** that own
their listener loop from startup through shutdown. The pod starts once, binds a port,
and handles thousands of requests within the same process lifetime.

Benchmarking a Spin component against a Docker container would measure fundamentally
different things:
- **Spin**: per-request WASM instantiation cost + handler execution time
- **Docker**: amortised server startup cost + handler execution time

The cold-start penalty, memory footprint, and CPU usage would all be influenced by
the instantiation model, not purely by the container/WASM runtime overhead. Such a
comparison would not be scientifically valid for the thesis research question.

SpinKube is therefore the most ecosystem-advanced WASM Kubernetes platform today, but
it answers a different research question: "how does a FaaS/serverless WASM deployment
compare to Docker?" — not the thesis question of "how do persistent WASM microservices
compare to Docker containers?"

---

### 7. wasmCloud

- **Maintainer**: wasmCloud project; CNCF Incubating (November 2024)
- **Underlying runtime**: Wasmtime
- **Design**: Distributed WASM application orchestration across clouds, Kubernetes, and
  edge nodes via a capability-provider model (`wasi:http`, `wasi:messaging`,
  `wasi:blobstore`). Not a pod-level container runtime.

**Why not chosen**: wasmCloud operates as a platform layer above Kubernetes, not as a
containerd shim. It does not create workloads comparable to Kubernetes pods for the
purposes of a Docker vs WASM pod-level benchmark.

---

## Summary Comparison

| Runtime | K8s shim | Long-running TCP | Rust wasip1 | TinyGo net/http | WASI P2 stable | Governance | Verdict |
|---|---|---|---|---|---|---|---|
| **WasmEdge** | Yes | Yes | Yes | Yes | No (in progress) | CNCF Sandbox | **Selected** |
| Wasmtime | Yes | Yes (wasip2) | Yes | No | Yes | Bytecode Alliance | TinyGo gap |
| Wasmer | Yes | Yes (WASIX) | Yes | No | Partial | Commercial | Proprietary lock-in |
| WAMR | No | No | Limited | No | Partial | Bytecode Alliance | No K8s shim |
| wazero | No | No | N/A | N/A | In progress | Tetrate | Embedded lib only |
| Spin/SpinKube | Yes | No (FaaS model) | Handler only | Handler only | Yes | CNCF Sandbox | Wrong exec model |
| wasmCloud | No (platform) | N/A | N/A | N/A | Yes | CNCF Incubating | Platform layer |

---

## Decision: WasmEdge

WasmEdge is chosen as the sole WASM runtime for the following reasons, ranked by weight:

**1. It is the only runtime that satisfies all hard constraints simultaneously.**
No other evaluated runtime provides a Kubernetes containerd shim, a long-running TCP
server model, functional Rust `std::net::TcpListener`, *and* functional TinyGo
`net/http` server behaviour in the same package. This combination is non-negotiable for
the experiment's design: both WASM variants must behave as persistent microservices
comparable to their Docker counterparts.

**2. CNCF Sandbox governance provides academic credibility.**
Unlike Wasmer (commercial) or proprietary extensions (WASIX), WasmEdge is governed
under the Cloud Native Computing Foundation, the same body that governs Kubernetes,
containerd, Prometheus, and other foundational cloud-native infrastructure. Results
obtained on a CNCF project are more defensible in an academic context than results on
a commercially-controlled runtime.

**3. Proprietary socket extension is a documented, deliberate choice — not a workaround.**
WasmEdge's POSIX socket extension predates the WASI 0.2 sockets specification and was
instrumental in proving that WASM could serve as a network-capable microservice runtime.
The extension's non-portability is explicitly noted as a thesis finding: it illustrates
the ecosystem maturity gap that WASI Preview 2 is designed to close.

**4. The TinyGo constraint is binding and eliminates Wasmtime.**
Wasmtime is the more standards-compliant and community-backed runtime (672 vs 215
contributors; Bytecode Alliance vs single company). If the thesis used only Rust, the
argument for Wasmtime + `wasm32-wasip2` would be strong. However, cross-language
coverage (Rust + Go) is a core experimental dimension — Go in the cloud-native space
is the dominant microservice language, and its WASM story (via TinyGo) must be
evaluated. This constraint forces the choice to WasmEdge.

**5. WasmEdge's WASI P2 trajectory is a thesis finding, not a disqualifier.**
The fact that WasmEdge's WASI P2 Component Model implementation is incomplete as of
early 2026 is itself data for the thesis: it demonstrates that WASM runtime maturity in
Kubernetes is uneven, and that the migration path from WASI P1 (proprietary socket
extensions) to WASI P2 (standardised `wasi:sockets`) is a real, ongoing engineering
challenge — not a solved problem. This finding strengthens the thesis's contribution
by grounding it in the current state of the ecosystem rather than an idealised future.

---

## WASI P1 vs WASI P2: Practical Difference for This Experiment

| Aspect | WASI Preview 1 (current) | WASI Preview 2 (future) |
|---|---|---|
| Binary format | Core WebAssembly module | Component Model (different format) |
| Sockets | WasmEdge proprietary extension | `wasi:sockets/tcp@0.2.0` (standardised) |
| HTTP | Not in spec (raw TCP) | `wasi:http/proxy@0.2.0` (handler model) |
| Portability | WasmEdge-only for TCP servers | Wasmtime, and eventually WasmEdge |
| Rust target | `wasm32-wasip1` | `wasm32-wasip2` (Rust Tier 2 since v1.82) |
| TinyGo target | `-target=wasip1` | `-target=wasip2` (experimental in TinyGo 0.40) |
| K8s deployment | Stable (runwasi v0.6.0) | Not yet stable on WasmEdge |

The thesis uses WASI Preview 1 throughout. The limitations this imposes — proprietary
socket ABI, runtime lock-in, single-threaded Rust HTTP server — are documented as
findings that characterise WASM's current maturity level as a microservice platform,
not as experimental flaws to be corrected before the benchmark is run.

---

## References

- WasmEdge GitHub: https://github.com/WasmEdge/WasmEdge
- Wasmtime GitHub: https://github.com/bytecodealliance/wasmtime
- containerd/runwasi: https://github.com/containerd/runwasi
- WASI Sockets Specification: https://github.com/WebAssembly/wasi-sockets
- Bytecode Alliance — WASI 0.2 Launch: https://bytecodealliance.org/articles/WASI-0.2
- SpinKube CNCF Sandbox: https://www.spinkube.dev/
- Rust Blog — wasm32-wasip2 Tier 2: https://blog.rust-lang.org/2024/11/26/wasip2-tier-2.html
- CNCF — WebAssembly on Kubernetes (Part 1): https://www.cncf.io/blog/2024/03/12/webassembly-on-kubernetes-from-containers-to-wasm-part-01/
- CNCF — WebAssembly on Kubernetes (Part 2): https://www.cncf.io/blog/2024/03/28/webassembly-on-kubernetes-the-practice-guide-part-02/
- wasmCloud CNCF Incubating: https://www.cncf.io/blog/2024/11/12/cncf-welcomes-wasmcloud-to-the-cncf-incubator/
- Fermyon — Introducing SpinKube: https://www.fermyon.com/blog/introducing-spinkube-fermyon-platform-for-k8s
- Docker WASM deprecation: https://docs.docker.com/desktop/features/wasm/
