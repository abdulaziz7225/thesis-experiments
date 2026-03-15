# Build stage: compile the Spin component (.wasm) using TinyGo's wasip2 target.
#
# The wasip2 target generates a WASI Preview 2 Component Model binary.
# Spin's TinyGo SDK provides the wasi:http/incoming-handler world bindings,
# enabling spinhttp.Handle() to register the HTTP handler at the component level.
#
# The resulting .wasm is pushed via `spin registry push` (NOT docker push).
# containerd-shim-spin expects a Spin OCI artifact, not a standard Docker image.
# See the README for the push workflow.
FROM tinygo/tinygo:0.40.1 AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN tinygo build -target=wasip2 -gc=conservative -opt=2 -o app.wasm .

# ── Final image ───────────────────────────────────────────────────────────────
# This scratch image is used only as a transport layer for the OCI artifact.
# `spin registry push` repacks the .wasm and spin.toml into a Spin OCI artifact
# with the correct media types that containerd-shim-spin-v2 expects.
# Do NOT use `docker push` — the SpinOperator will reject a plain Docker image.
FROM scratch
COPY --from=builder /app/app.wasm /app.wasm
COPY --from=builder /app/spin.toml /spin.toml
