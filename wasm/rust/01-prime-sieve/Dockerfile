# ── Stage 1: cross-compile to wasm32-wasip1 ──────────────────────────────────
FROM rust:1.94 AS builder

RUN rustup target add wasm32-wasip1

WORKDIR /app

# Cache dependency compilation layer.
COPY .cargo  ./.cargo
COPY Cargo.toml ./
RUN mkdir -p src && echo 'fn main() {}' > src/main.rs \
    && cargo build --target wasm32-wasip1 --release \
    && rm -rf src

# Build application.
COPY src ./src
RUN touch src/main.rs \
    && cargo build --target wasm32-wasip1 --release

# ── Stage 2: minimal OCI image containing only the .wasm binary ──────────────
# The WasmEdge runtime (via crun OCI runtime) extracts and executes the binary
# named in the container's ENTRYPOINT. The "wasmedge" RuntimeClass in k8s
# routes pod creation through crun → libwasmedge.so (system WasmEdge ≥ 0.14).
FROM scratch

COPY --from=builder \
    /app/target/wasm32-wasip1/release/prime-sieve-wasm.wasm \
    /app.wasm

ENTRYPOINT ["/app.wasm"]
