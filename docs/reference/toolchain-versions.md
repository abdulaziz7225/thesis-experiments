# Pinned toolchain versions

Every external component the experiments depend on, with the version
pinned and where the pin is enforced.

"Pinned in" links point to files in the sibling
[thesis-infra-setup](https://github.com/abdulaziz7225/thesis-infra-setup)
repo where applicable, and to in-tree paths in this repo otherwise.

| Component                   | Version       | Pinned in                                                                                                                                          | Notes                                                            |
| --------------------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Kubernetes (kubeadm)        | v1.34.x       | [thesis-infra-setup/cloud-init.sh](https://github.com/abdulaziz7225/thesis-infra-setup/blob/main/cloud-init.sh)                                    | Upstream reference platform; Flannel CNI                         |
| containerd-shim-spin-v2     | v0.17.0       | [thesis-infra-setup/cloud-init.sh](https://github.com/abdulaziz7225/thesis-infra-setup/blob/main/cloud-init.sh)                                    | SpinKube Wasm shim (Wasmtime/Cranelift)                          |
| SpinOperator                | v0.6.1        | [thesis-infra-setup/Makefile](https://github.com/abdulaziz7225/thesis-infra-setup/blob/main/Makefile) (Helm)                                       | Manages `SpinApp` CRDs; requires cert-manager                    |
| cert-manager                | v1.16.3       | [thesis-infra-setup/Makefile](https://github.com/abdulaziz7225/thesis-infra-setup/blob/main/Makefile) (Helm)                                       | Prerequisite for SpinOperator webhooks                           |
| Spin CLI                    | v3+           | local install                                                                                                                                      | `spin registry push` for WASI P2 OCI images                      |
| cargo-component             | latest        | local install                                                                                                                                      | Builds Rust WASI P2 components (`cargo component build`)         |
| k6                          | latest stable | [thesis-infra-setup `setup-local` target](https://github.com/abdulaziz7225/thesis-infra-setup/blob/main/Makefile)                                  | HTTP load generator                                              |
| Rust (Docker + Spin)        | 1.94          | Dockerfile / Cargo.toml                                                                                                                            | Current stable                                                   |
| Go (Docker)                 | 1.26          | Dockerfile                                                                                                                                         | Current stable                                                   |
| Go (TinyGo builds **only**) | **1.23.12**   | local install via `golang.org/dl/go1.23.12`                                                                                                        | TinyGo 0.40.1 rejects ≥ 1.26; 1.24/1.25 panic on `crypto/sha256` |
| TinyGo (Spin)               | 0.40.1        | local install                                                                                                                                      | `-target=wasip1`; wasip2 hardwires `wasi:cli/command` world      |
| spin-sdk (Rust)             | 5.2.0         | `wasm/rust/*/Cargo.toml`                                                                                                                           | `#[http_component]` macro for WASI P2 HTTP handlers              |
| spin-go-sdk (TinyGo)        | v2.2.1        | `wasm/tinygo/*/go.mod`                                                                                                                             | Official Spin Go SDK; exports `fermyon:spin/inbound-http`        |

## Rust release profile (all eight Rust crates)

```toml
[profile.release]
opt-level     = 3       # docker variants
opt-level     = "s"     # spin variants (size-tuned for wasm)
lto           = true
codegen-units = 1
strip         = true
panic         = "abort"
```

## Go release flags (all five Go binaries)

```
CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o <name> .
```

## TinyGo release flags

```
PATH="$HOME/sdk/go1.23.12/bin:$PATH" \
  tinygo build -target=wasip1 -gc=conservative -opt=2 -no-debug -o app.wasm .
```

## Hardware

Single Hetzner Cloud `ccx23` VM (4 vCPU dedicated, 16 GB RAM). All
experiments run on this single node — control plane and workloads
share the same cores. See
[runtime-choice.md](runtime-choice.md) for why this configuration was
picked, and [troubleshooting.md](troubleshooting.md) for the failure
modes that single-node arrangement is most prone to (cluster collapse
under sustained load).
