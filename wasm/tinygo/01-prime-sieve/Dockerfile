# ── Stage 1: compile to WASI with TinyGo ─────────────────────────────────────
# Version note: upgraded from 0.27.0 to 0.40.1
# TinyGo 0.27.0 relied on net/http which used WasmEdge's WASI socket extension
# ABI implicitly. WasmEdge 0.14.x changed that ABI, causing sock_open to fail
# silently and ListenAndServe to return nil → process exits with code 0.
# TinyGo 0.28+ has the Netdev regression (issues #4880/#4630, still open in 0.40.x)
# making net/http permanently broken for wasip1.
#
# This image no longer uses net/http. It calls WasmEdge socket extension
# functions directly via //go:wasmimport (same approach as Rust's
# wasmedge_wasi_socket), so the TinyGo version pin is no longer needed.
FROM tinygo/tinygo:0.40.1 AS builder

WORKDIR /app

COPY go.mod   ./
COPY main.go  ./
COPY server.go ./

# -target=wasi     : WASI P1 target (alias still valid in TinyGo 0.40.1)
# -gc=conservative : required — keeps heap objects pinned for //go:wasmimport
#                    pointer params that are stored as uint32 in ABI structs
# -opt=2           : optimise for speed
RUN tinygo build \
        -target=wasi \
        -gc=conservative \
        -opt=2 \
        -o app.wasm \
        .

# ── Stage 2: minimal OCI image containing only the .wasm binary ──────────────
FROM scratch

COPY --from=builder /app/app.wasm /app.wasm

ENTRYPOINT ["/app.wasm"]
