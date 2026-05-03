# WebAssembly Runtime Selection Rationale

## Thesis Context

This document records the reasoning behind the choice of **SpinKube (Wasmtime/Cranelift)**
as the primary WebAssembly runtime for the experiment comparing Docker (OCI/runc) containers
against WebAssembly workloads in a Kubernetes cluster.

The experiment deploys four primary variants of the same HTTP microservice benchmark:

| Variant | Runtime | WASI | K8s runtimeClassName |
|---|---|---|---|
| `wasm-rust` | Wasmtime/Cranelift (via Spin) | Preview 2 | `wasmtime-spin` |
| `wasm-tinygo` | Wasmtime/Cranelift (via Spin) | Preview 2 | `wasmtime-spin` |
| `docker-rust` | runc (native) | — | *(none — cluster default)* |
| `docker-golang` | runc (native) | — | *(none — cluster default)* |

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

### 1. Wasmtime

- **Maintainer**: Bytecode Alliance (non-profit); primary contributors: Fastly, Intel,
  Mozilla, Microsoft, Arm, Google, Shopify
- **Repository**: github.com/bytecodealliance/wasmtime
- **Stars / Contributors**: ~17,700 stars / 672 contributors (largest community of all
  evaluated runtimes)
- **Latest release**: v42.0.1 (February 2026); monthly major releases
- **Corporate backing**: Bytecode Alliance member organisations (neutral non-profit)
- **Kubernetes shim**: `io.containerd.wasmtime.v1` — part of containerd/runwasi
- **WASI P2**: Full support — Wasmtime is the **reference implementation** of
  WASI 0.2. Includes production-ready `wasi:sockets/tcp@0.2.0` and `wasi:http/proxy@0.2.0`.

**Role in this thesis**: Wasmtime is the JIT engine embedded inside Fermyon Spin. When this
thesis deploys SpinKube, it is deploying Wasmtime/Cranelift directly — Spin is the WASI
framework layer on top of it. Wasmtime's Bytecode Alliance governance model (neutral non-profit,
broad corporate membership) provides strong academic credibility for the chosen runtime stack.

---

### 2. Wasmer

- **Maintainer**: Wasmer Inc. (commercial company)
- **Repository**: github.com/wasmerio/wasmer
- **Stars / Contributors**: ~20,500 stars (highest of all runtimes)
- **Corporate backing**: Wasmer Inc. (VC-backed)
- **WASI P2**: Partial — Wasmer's primary differentiator is **WASIX**, a proprietary
  POSIX superset outside of the WASI standard. WASIX is not portable to other runtimes.

**Why not chosen**:

1. **Proprietary lock-in**: WASIX is a Wasmer Inc. invention not endorsed by the Bytecode
   Alliance or the W3C WebAssembly Working Group. Results on WASIX are not portable.
2. **Commercial conflict of interest**: Wasmer's primary incentive is Wasmer Cloud adoption.
   Academic benchmarks should prefer runtimes governed by neutral bodies.

---

### 3. WAMR (WebAssembly Micro Runtime)

- **Maintainer**: Bytecode Alliance; primary contributor: Intel
- **Repository**: github.com/bytecodealliance/wasm-micro-runtime
- **Kubernetes shim**: **None** — GitHub issue #337 to add WAMR to containerd/runwasi is
  open and unmerged as of early 2026.
- **Design target**: IoT, embedded systems, Trusted Execution Environments.

**Why not chosen**: The absence of a containerd shim is a hard disqualifier. WAMR cannot
create pod-level Kubernetes workloads comparable to Docker containers.

---

### 4. wazero

- **Maintainer**: Tetrate
- **Repository**: github.com/tetratelabs/wazero
- **Kubernetes shim**: **None** — wazero is an embeddable Go library, not a standalone runtime.

**Why not chosen**: wazero is architecturally incompatible — it is a library embedded inside
Go applications. It cannot replace a pod-level container runtime in Kubernetes.

---

### 5. Spin / SpinKube

- **Maintainer**: Fermyon Technologies; SpinKube donated to CNCF (Sandbox, January 2025)
- **Repository**: github.com/spinframework/spin + github.com/spinkube
- **Corporate backing**: Fermyon, Microsoft, SUSE, Liquid Reply
- **Underlying runtime**: **Wasmtime (Cranelift JIT)** — Spin embeds Wasmtime directly.
- **Kubernetes shim**: `io.containerd.spin.v2` — `containerd-shim-spin-v2` implements the
  containerd shim v2 protocol and embeds Spin (which embeds Wasmtime). The SpinOperator
  (CNCF Sandbox) manages Spin workloads via the `SpinApp` CRD.
- **WASI P2**: Full support via Wasmtime; `wasi:http/incoming-handler@0.2.0`

**Execution model**: Spin uses the `wasi:http/incoming-handler` model — Spin owns the TCP
listener and HTTP parsing; for each incoming request it calls the component's `handle` export.
This is the standardised WASI P2 HTTP interface; every mature WASI P2 HTTP framework uses it.

**Why SpinKube is the primary choice**:

1. **WASI P2 is the current ecosystem direction** — `wasi:http/incoming-handler` is the
   standardised interface in WASI 0.2 and the production-ready path for HTTP microservices.

2. **Standard library support** — With SpinKube:
   - Rust: `#[http_component]` macro via `spin-sdk = "3"` targeting `wasm32-wasip2`. No custom TCP loop.
   - TinyGo: `spinhttp.Handle()` via `github.com/spinframework/spin-go-sdk/v2` targeting `wasip1`.
     TinyGo's `wasip2` target hardwires the `wasi:cli/command` world and cannot export
     `wasi:http/incoming-handler`; the Spin Go SDK's CGo layer exports `fermyon:spin/inbound-http`
     instead, which Spin accepts as a valid HTTP trigger interface.

3. **Bytecode Alliance runtime** — Wasmtime (inside Spin) is the Bytecode Alliance reference
   implementation of WASI 0.2, with the broadest community and most rigorous standards
   compliance.

4. **CNCF Sandbox governance** — SpinKube was accepted to CNCF Sandbox in January 2025,
   providing the academic legitimacy required for the thesis citation.

5. **Single-replica baseline for resource fairness** — The supervisor requires that all variants
   operate within the same resource capacity. For the limited-mode baseline the SpinApp is run
   with `spec.replicas: 1` and the WASI P1/P2 component handles one request at a time on a
   single Wasmtime instance, matching the single-thread constraint imposed on the Docker
   variants (`GOMAXPROCS=1` for docker-golang, `TOKIO_WORKER_THREADS=1` for docker-rust). Earlier
   versions of Spin exposed a `max_instances` knob in `spin.toml`; in Spin 2.x
   (`spin_manifest_version = 2`) that field was removed, so concurrency is controlled at the
   pod/replica level instead.

---

### 6. wasmCloud

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

2. **Standard framework code** — Both the Rust (`#[http_component]`) and TinyGo
   (`spinhttp.Handle()`) implementations are idiomatic, low-boilerplate handler functions.
   No custom TCP listener, no `//go:wasmimport` socket directives, no proprietary host calls.

3. **Bytecode Alliance reference runtime** — Wasmtime (inside Spin) is the most widely
   used and best-maintained WASM runtime, governed by the neutral Bytecode Alliance.

4. **CNCF Sandbox legitimacy** — SpinKube's January 2025 CNCF Sandbox acceptance establishes
   the project's governance maturity for academic citation.

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
- [wasmCloud CNCF Incubating](https://www.cncf.io/blog/2024/11/12/cncf-welcomes-wasmcloud-to-the-cncf-incubator/)
