# ── Stage 1: build ──────────────────────────────────────────────────────────
FROM rust:1.94-alpine AS builder

RUN apk add --no-cache musl-dev

WORKDIR /app

COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo 'fn main() {}' > src/main.rs \
    && cargo build --release \
    && rm -rf src

COPY src ./src
RUN touch src/main.rs && cargo build --release

# ── Stage 2: minimal runtime image ──────────────────────────────────────────
FROM scratch

COPY --from=builder /app/target/release/json-roundtrip /json-roundtrip
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

EXPOSE 8080

ENTRYPOINT ["/json-roundtrip"]
