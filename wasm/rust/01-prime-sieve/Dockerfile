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
# WasmEdge's containerd shim (runwasi) extracts and executes the binary
# named in the container's ENTRYPOINT.
FROM scratch

COPY --from=builder \
    /app/target/wasm32-wasip1/release/prime-sieve-wasm.wasm \
    /app.wasm

ENTRYPOINT ["/app.wasm"]
