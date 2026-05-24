# Build and push — Wasm variants

Eight `.wasm` artefacts come out of this file: `wasm-rust` and
`wasm-tinygo` for each of the four examples. Each is wrapped in a
**Spin OCI artifact** (not a Docker image) and pushed via
`spin registry push` — see the box at the end for why this matters.

Prerequisites:

- Spin CLI v3+
- `cargo-component` (for the Rust variants)
- TinyGo 0.40.1 **plus** Go 1.23.12 installed via `golang.org/dl/`
  (for the TinyGo variants — see the next section)

All four are covered in [../setup/01-prerequisites.md](../setup/01-prerequisites.md).

```bash
export DOCKER_USER=<YOUR_DOCKERHUB_USERNAME>
```

## TinyGo + Go 1.23.12 PATH override — required

> TinyGo 0.40.1 rejects Go ≥ 1.26 outright, and Go 1.24 / 1.25 trigger
> `crypto/sha256` panics inside the TinyGo wasip1 runtime. **Go 1.23.12
> is the only known-good version.** The TinyGo build commands below
> prepend `~/sdk/go1.23.12/bin` to `PATH` so TinyGo invokes the right Go
> toolchain (installed in
> [../setup/01-prerequisites.md](../setup/01-prerequisites.md) — does
> **not** affect your system Go). Wasm + Rust commands are unaffected.

## All four Wasm + Rust variants

```bash
# 01 prime sieve
cd wasm/rust/01-prime-sieve
cargo component build --release
spin registry push docker.io/${DOCKER_USER}/prime-sieve-wasm-rust:latest
cd ../../..

# 02 memory bandwidth
cd wasm/rust/02-memory-bandwidth
cargo component build --release
spin registry push docker.io/${DOCKER_USER}/memory-bandwidth-wasm-rust:latest
cd ../../..

# 03 HTTP fan-out (I/O-bound)
cd wasm/rust/03-http-fanout
cargo component build --release
spin registry push docker.io/${DOCKER_USER}/http-fanout-wasm-rust:latest
cd ../../..

# 04 JSON round-trip
cd wasm/rust/04-json-roundtrip
cargo component build --release
spin registry push docker.io/${DOCKER_USER}/json-roundtrip-wasm-rust:latest
cd ../../..
```

The `[profile.release]` block in each crate's `Cargo.toml` sets
`opt-level="s"` (size-tuned), `lto=true`, `codegen-units=1`,
`strip=true`, `panic="abort"`.

## All four Wasm + TinyGo variants

```bash
# 01 prime sieve
cd wasm/tinygo/01-prime-sieve
PATH="$HOME/sdk/go1.23.12/bin:$PATH" \
  tinygo build -target=wasip1 -gc=conservative -opt=2 -no-debug -o app.wasm .
spin registry push docker.io/${DOCKER_USER}/prime-sieve-wasm-tinygo:latest
cd ../../..

# 02 memory bandwidth
cd wasm/tinygo/02-memory-bandwidth
PATH="$HOME/sdk/go1.23.12/bin:$PATH" \
  tinygo build -target=wasip1 -gc=conservative -opt=2 -no-debug -o app.wasm .
spin registry push docker.io/${DOCKER_USER}/memory-bandwidth-wasm-tinygo:latest
cd ../../..

# 03 HTTP fan-out (I/O-bound)
cd wasm/tinygo/03-http-fanout
PATH="$HOME/sdk/go1.23.12/bin:$PATH" \
  tinygo build -target=wasip1 -gc=conservative -opt=2 -no-debug -o app.wasm .
spin registry push docker.io/${DOCKER_USER}/http-fanout-wasm-tinygo:latest
cd ../../..

# 04 JSON round-trip
cd wasm/tinygo/04-json-roundtrip
PATH="$HOME/sdk/go1.23.12/bin:$PATH" \
  tinygo build -target=wasip1 -gc=conservative -opt=2 -no-debug -o app.wasm .
spin registry push docker.io/${DOCKER_USER}/json-roundtrip-wasm-tinygo:latest
cd ../../..
```

TinyGo build flags: `-target=wasip1` picks the WASI Preview 1 target
(required — TinyGo's wasip2 target hardwires `wasi:cli/command` and
cannot export Spin's HTTP handler interface), `-gc=conservative`,
`-opt=2`, `-no-debug` strips debug info.

## Why `spin registry push` and not `docker push`?

`spin registry push` produces a **Spin-specific OCI artifact** with media
types `application/vnd.fermyon.spin.manifest.v2+json` and friends. The
`containerd-shim-spin-v2` runtime on the cluster knows how to recognise
and execute these artefacts; the plain Docker engine and standard OCI
tooling do not. If you `docker push` a `.wasm` instead, the SpinOperator
will reject the resulting image at admission time.

## Next

After all eight `.wasm` artefacts are pushed, continue with
[../operate/deploy.md](../operate/deploy.md) to bring an experiment up
on the cluster.

For 03 (HTTP fan-out, I/O-bound) you also need the small `io-echo`
backend image: see [io-echo-backend.md](io-echo-backend.md).
