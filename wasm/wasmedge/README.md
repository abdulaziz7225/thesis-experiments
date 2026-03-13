# WasmEdge / WASI Preview 1 — Optional Comparison Variants

This directory contains the **optional** WasmEdge/WASI P1 source code, kept as a reference
comparison for Appendix B of the thesis.

## Why these are here

The primary Wasm variants (`wasm/rust/`, `wasm/tinygo/`) use **SpinKube/Wasmtime (WASI P2)**
as the production-ready current ecosystem. These WasmEdge variants represent the earlier
WASI P1 approach and are not part of the main benchmark.

They are preserved because:

1. They document the constraints of WASI P1: proprietary `wasmedge_wasi_socket` ABI for Rust,
   `//go:wasmimport` socket bindings for TinyGo, single-threaded accept-loop HTTP model.
2. The P1 benchmark results (throughput ceiling ~24 RPS, concurrency bottleneck) are discussed
   in the thesis as a historical comparison and motivation for the WASI P2 migration.

## Contents

- `rust/01-prime-sieve/` — Rust + WasmEdge WASI P1; uses `wasmedge_wasi_socket 0.5.5`
- `tinygo/01-prime-sieve/` — TinyGo + WasmEdge WASI P1; uses `//go:wasmimport` socket ABI

## How to deploy (optional)

```bash
# In thesis-infra-setup — enable WasmEdge infrastructure:
ENABLE_WASMEDGE=true bash cloud-init.sh
make label-node-wasmedge
make deploy-wasmedge

# Build and push images:
docker build -t docker.io/abdulaziz7225/prime-sieve-wasm-rust:latest rust/01-prime-sieve/
docker push docker.io/abdulaziz7225/prime-sieve-wasm-rust:latest

docker build -t docker.io/abdulaziz7225/prime-sieve-wasm-tinygo:latest tinygo/01-prime-sieve/
docker push docker.io/abdulaziz7225/prime-sieve-wasm-tinygo:latest

# Deploy to cluster:
kubectl apply -f ../../k8s/01-prime-sieve/optional/wasm-rust.yaml
kubectl apply -f ../../k8s/01-prime-sieve/optional/wasm-tinygo.yaml
```

NodePorts: `wasm-rust` → 30085, `wasm-tinygo` → 30086.
