# Build and push — Docker variants

Eight images come out of this file: `docker-rust` and `docker-golang` for
each of the four examples. Plus the small `io-echo` backend image (covered
in [io-echo-backend.md](io-echo-backend.md)) used by 03.

Prerequisites: [Docker daemon](../setup/01-prerequisites.md) and a Docker
Hub login (`docker login`) for whichever registry you push to.

Export your Docker Hub username once:

```bash
export DOCKER_USER=<YOUR_DOCKERHUB_USERNAME>
```

## All four Docker + Rust variants

```bash
# 01 prime sieve
docker build -t docker.io/${DOCKER_USER}/prime-sieve-docker-rust:latest \
    docker/rust/01-prime-sieve/
docker push docker.io/${DOCKER_USER}/prime-sieve-docker-rust:latest

# 02 memory bandwidth
docker build -t docker.io/${DOCKER_USER}/memory-bandwidth-docker-rust:latest \
    docker/rust/02-memory-bandwidth/
docker push docker.io/${DOCKER_USER}/memory-bandwidth-docker-rust:latest

# 03 HTTP fan-out (I/O-bound)
docker build -t docker.io/${DOCKER_USER}/http-fanout-docker-rust:latest \
    docker/rust/03-http-fanout/
docker push docker.io/${DOCKER_USER}/http-fanout-docker-rust:latest

# 04 JSON round-trip
docker build -t docker.io/${DOCKER_USER}/json-roundtrip-docker-rust:latest \
    docker/rust/04-json-roundtrip/
docker push docker.io/${DOCKER_USER}/json-roundtrip-docker-rust:latest
```

## All four Docker + Go variants

```bash
# 01 prime sieve
docker build -t docker.io/${DOCKER_USER}/prime-sieve-docker-golang:latest \
    docker/golang/01-prime-sieve/
docker push docker.io/${DOCKER_USER}/prime-sieve-docker-golang:latest

# 02 memory bandwidth
docker build -t docker.io/${DOCKER_USER}/memory-bandwidth-docker-golang:latest \
    docker/golang/02-memory-bandwidth/
docker push docker.io/${DOCKER_USER}/memory-bandwidth-docker-golang:latest

# 03 HTTP fan-out (I/O-bound)
docker build -t docker.io/${DOCKER_USER}/http-fanout-docker-golang:latest \
    docker/golang/03-http-fanout/
docker push docker.io/${DOCKER_USER}/http-fanout-docker-golang:latest

# 04 JSON round-trip
docker build -t docker.io/${DOCKER_USER}/json-roundtrip-docker-golang:latest \
    docker/golang/04-json-roundtrip/
docker push docker.io/${DOCKER_USER}/json-roundtrip-docker-golang:latest
```

## How the Dockerfiles are built

All eight Dockerfiles share the same shape:

1. **Stage 1 — builder**: Alpine-based language image (`rust:1.94-alpine`
   or `golang:1.26-alpine`). For Rust, a dummy `src/main.rs` is compiled
   first so dependency artefacts cache separately from the real source.
2. **Stage 2 — runtime**: `FROM scratch`. Only the stripped binary and
   the system CA bundle are copied in. Result: < 10 MB images, no shell,
   no libc, no attack surface beyond the binary itself.

Build flags:

- Rust: `cargo build --release`. The release profile in each crate's
  `Cargo.toml` sets `opt-level=3`, `lto=true`, `codegen-units=1`,
  `strip=true`, `panic="abort"` (see
  [../reference/toolchain-versions.md](../reference/toolchain-versions.md)
  for the full table).
- Go: `CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o <bin> .`.
  `-s` strips the symbol table, `-w` strips DWARF debug info,
  `-trimpath` removes embedded file paths (reproducible builds),
  `CGO_ENABLED=0` produces a static binary.

## Next

After all eight images are pushed (plus the `io-echo` backend for 03 —
see [io-echo-backend.md](io-echo-backend.md)), continue with
[wasm-variants.md](wasm-variants.md) for the SpinKube side, then
[../operate/deploy.md](../operate/deploy.md) to bring an experiment up
on the cluster.
