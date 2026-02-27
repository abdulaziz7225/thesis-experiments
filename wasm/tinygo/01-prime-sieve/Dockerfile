# ── Stage 1: compile to wasm32-wasip1 with TinyGo ───────────────────────────
FROM tinygo/tinygo:0.40.0 AS builder

WORKDIR /app

COPY go.mod  ./
COPY main.go ./

# -target=wasip1   : WASI Preview 1 (compatible with WasmEdge socket extension)
# -gc=conservative : safe GC for long-running servers (default for wasip1)
# -opt=2           : optimise for speed
RUN tinygo build \
        -target=wasip1 \
        -gc=conservative \
        -opt=2 \
        -o app.wasm \
        .

# ── Stage 2: minimal OCI image containing only the .wasm binary ──────────────
FROM scratch

COPY --from=builder /app/app.wasm /app.wasm

ENTRYPOINT ["/app.wasm"]
