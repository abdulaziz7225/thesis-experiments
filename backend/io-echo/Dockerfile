# ── Stage 1: build ──────────────────────────────────────────────────────────
FROM golang:1.26-alpine AS builder

WORKDIR /app

COPY go.mod ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o io-echo .

# ── Stage 2: minimal runtime image ──────────────────────────────────────────
FROM scratch

COPY --from=builder /app/io-echo /io-echo

EXPOSE 8080

ENTRYPOINT ["/io-echo"]
