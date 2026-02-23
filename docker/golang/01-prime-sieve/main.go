package main

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"time"
)

// ── Response ────────────────────────────────────────────────────────────────
type SieveResponse struct {
	Runtime   string `json:"runtime"`
	Limit     int    `json:"limit"`
	Count     int    `json:"count"`
	Primes    []int  `json:"primes,omitempty"`
	ElapsedUs int64  `json:"elapsed_us"`
}

// ── Algorithm ───────────────────────────────────────────────────────────────
// sieveOfEratosthenes returns every prime p where 2 ≤ p ≤ limit.
func sieveOfEratosthenes(limit int) []int {
	if limit < 2 {
		return nil
	}

	composite := make([]bool, limit+1)
	for i := 2; i*i <= limit; i++ {
		if !composite[i] {
			for j := i * i; j <= limit; j += i {
				composite[j] = true
			}
		}
	}

	primes := make([]int, 0, limit/10) // rough pre-allocation
	for i := 2; i <= limit; i++ {
		if !composite[i] {
			primes = append(primes, i)
		}
	}
	return primes
}

// ── Handlers ────────────────────────────────────────────────────────────────
func sieveHandler(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	limit := 10_000
	if raw := q.Get("limit"); raw != "" {
		if v, err := strconv.Atoi(raw); err == nil && v > 0 {
			if v > 10_000_000 {
				v = 10_000_000
			}
			limit = v
		}
	}
	noList := q.Get("no_list") == "true" || q.Get("no_list") == "1"

	start := time.Now()
	primes := sieveOfEratosthenes(limit)
	elapsed := time.Since(start).Microseconds()

	slog.Info("sieve completed",
		"limit", limit,
		"count", len(primes),
		"elapsed_us", elapsed,
	)

	resp := SieveResponse{
		Runtime:   "golang-docker",
		Limit:     limit,
		Count:     len(primes),
		ElapsedUs: elapsed,
	}
	if !noList {
		resp.Primes = primes
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		slog.Error("encode error", "err", err)
	}
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
}

// ── Entry point ──────────────────────────────────────────────────────────────
func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(logger)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /sieve", sieveHandler)
	mux.HandleFunc("GET /health", healthHandler)

	addr := ":8080"
	slog.Info("server starting", "addr", addr)

	if err := http.ListenAndServe(addr, mux); err != nil {
		slog.Error("server error", "err", err)
		os.Exit(1)
	}
}
