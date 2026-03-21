package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"time"
)

// ── Response ─────────────────────────────────────────────────────────────────
type MemBwResponse struct {
	Runtime   string `json:"runtime"`
	SizeKb    int    `json:"size_kb"`
	Sha256    string `json:"sha256"`
	ElapsedUs int64  `json:"elapsed_us"`
}

// ── Handler ───────────────────────────────────────────────────────────────────
func memBwHandler(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	sizeKb := 64
	if raw := q.Get("size_kb"); raw != "" {
		if v, err := strconv.Atoi(raw); err == nil && v > 0 {
			if v > 10240 {
				v = 10240
			}
			sizeKb = v
		}
	}
	noHash := q.Get("no_hash") == "true" || q.Get("no_hash") == "1"

	start := time.Now()

	// Allocate and fill buffer with deterministic pattern.
	buf := make([]byte, sizeKb*1024)
	for i := range buf {
		buf[i] = byte(i & 0xFF)
	}

	hashStr := ""
	if !noHash {
		sum := sha256.Sum256(buf)
		hashStr = hex.EncodeToString(sum[:])
	}

	elapsed := time.Since(start).Microseconds()

	slog.Info("membw completed", "size_kb", sizeKb, "elapsed_us", elapsed)

	resp := MemBwResponse{
		Runtime:   "golang-docker",
		SizeKb:    sizeKb,
		Sha256:    hashStr,
		ElapsedUs: elapsed,
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		slog.Error("encode error", "err", err)
	}
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
}

// ── Entry point ───────────────────────────────────────────────────────────────
func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(logger)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /membw", memBwHandler)
	mux.HandleFunc("GET /health", healthHandler)

	addr := ":8080"
	slog.Info("server starting", "addr", addr)

	if err := http.ListenAndServe(addr, mux); err != nil {
		slog.Error("server error", "err", err)
		os.Exit(1)
	}
}
