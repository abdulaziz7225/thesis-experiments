# Build stage: compile the Spin component (.wasm) using cargo-component.
#
# cargo-component wraps cargo to produce WASI P2 Component Model binaries.
# It generates WIT bindings and passes --target wasm32-wasip1 (cargo-component
# currently generates P1-format modules; Spin lifts them to P2 at runtime).
#
# The resulting .wasm is pushed via `spin registry push` (NOT docker push).
# containerd-shim-spin expects a Spin OCI artifact, not a standard Docker image.
# See the README for the push workflow.
FROM rust:1.94 AS builder

# Install cargo-component for WASI P2 Component Model builds.
RUN cargo install cargo-component --locked

# Add the wasip1 target (cargo-component builds wasip1 modules that Spin adapts to WASI P2).
RUN rustup target add wasm32-wasip1

WORKDIR /app
COPY . .

RUN cargo component build --release

# ── Final image ───────────────────────────────────────────────────────────────
# This scratch image is used only as a transport layer for the OCI artifact.
# `spin registry push` repacks the .wasm and spin.toml into a Spin OCI artifact
# with the correct media types that containerd-shim-spin-v2 expects.
# Do NOT use `docker push` — the SpinOperator will reject a plain Docker image.
FROM scratch
COPY --from=builder /app/target/wasm32-wasip1/release/prime_sieve_spin.wasm /prime_sieve_spin.wasm
COPY --from=builder /app/spin.toml /spin.toml
