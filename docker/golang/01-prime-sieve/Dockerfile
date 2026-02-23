# ── Stage 1: build ──────────────────────────────────────────────────────────
FROM golang:1.26-alpine AS builder

WORKDIR /app

COPY go.mod ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o prime-sieve .

# ── Stage 2: minimal runtime image ──────────────────────────────────────────
FROM scratch

COPY --from=builder /app/prime-sieve /prime-sieve
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

EXPOSE 8080

ENTRYPOINT ["/prime-sieve"]
