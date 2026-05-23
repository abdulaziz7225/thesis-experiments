# ── Stage 1: build ──────────────────────────────────────────────────────────
FROM golang:1.26-alpine AS builder

WORKDIR /app

COPY go.mod ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o memory-bandwidth .

# ── Stage 2: minimal runtime image ──────────────────────────────────────────
FROM scratch

COPY --from=builder /app/memory-bandwidth /memory-bandwidth
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

EXPOSE 8080

ENTRYPOINT ["/memory-bandwidth"]
