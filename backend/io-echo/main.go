// io-echo — minimal HTTP delay/echo backend for the 03-http-fanout I/O-bound experiment.
//
// This service is NOT part of the comparison matrix. It is the outbound HTTP target
// that the four fan-out variants (wasm-rust, wasm-tinygo, docker-rust, docker-golang)
// call. By holding the per-request latency floor stable (and the response size fixed),
// variation in measured aggregate throughput/latency in the four fan-out variants is
// attributable to runtime/language overhead — not backend noise.
//
// API:
//   GET /health                         → 200
//   GET /echo?delay_ms=D&size_b=B       → sleeps D ms, returns B bytes of payload.
//     delay_ms default 50, max 1000
//     size_b   default 256, max 65536
//
// Build: docker build -t docker.io/abdulaziz7225/io-echo-backend:latest backend/io-echo/

package main

import (
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"time"
)

const (
	defaultDelayMs = 50
	maxDelayMs     = 1000
	defaultSizeB   = 256
	maxSizeB       = 65536
)

func clampInt(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func parseIntParam(raw string, defVal, maxVal int) int {
	if raw == "" {
		return defVal
	}
	v, err := strconv.Atoi(raw)
	if err != nil || v < 0 {
		return defVal
	}
	return clampInt(v, 0, maxVal)
}

func echoHandler(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	delayMs := parseIntParam(q.Get("delay_ms"), defaultDelayMs, maxDelayMs)
	sizeB := parseIntParam(q.Get("size_b"), defaultSizeB, maxSizeB)

	time.Sleep(time.Duration(delayMs) * time.Millisecond)

	payload := make([]byte, sizeB)
	for i := range payload {
		payload[i] = 'A' + byte(i%26)
	}

	w.Header().Set("Content-Type", "application/octet-stream")
	w.Header().Set("X-Delay-Ms", strconv.Itoa(delayMs))
	w.Header().Set("X-Size-B", strconv.Itoa(sizeB))
	_, _ = w.Write(payload)
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(logger)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /echo", echoHandler)
	mux.HandleFunc("GET /health", healthHandler)

	addr := ":8080"
	slog.Info("io-echo backend starting", "addr", addr,
		"role", "outbound target for 03-http-fanout I/O-bound experiment")

	if err := http.ListenAndServe(addr, mux); err != nil {
		slog.Error("server error", "err", err)
		os.Exit(1)
	}
}
