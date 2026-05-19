// Go + Docker (runc) — HTTP fan-out HTTP service (I/O-bound experiment).
//
// On each inbound request, dispatch N concurrent outbound HTTP GETs to the
// in-cluster `io-echo` backend; the backend sleeps for delay_ms before
// responding, so the handler is dominated by outbound I/O wait rather than
// CPU work. Concurrent outbound is via sync.WaitGroup + goroutines over a
// shared http.Client with a tuned transport — the idiomatic Go I/O pattern.
//
// This is the docker-runc counterpart to the wasm-tinygo Spin component; they
// expose the same /fanout HTTP API to keep the comparison apples-to-apples.

package main

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"
)

const (
	backendURL     = "http://io-echo.http-fanout.svc.cluster.local/echo"
	defaultN       = 5
	maxN           = 20
	defaultDelayMs = 50
	maxDelayMs     = 1000
)

// ── Response ─────────────────────────────────────────────────────────────────
type FanoutResponse struct {
	Runtime   string `json:"runtime"`
	N         int    `json:"n"`
	DelayMs   int    `json:"delay_ms"`
	OkCount   int    `json:"ok_count"`
	ErrCount  int    `json:"err_count"`
	ElapsedUs int64  `json:"elapsed_us"`
	Responses []int  `json:"responses,omitempty"`
}

// Shared client — tuned transport for keep-alive against the io-echo backend.
var httpClient = &http.Client{
	Timeout: 5 * time.Second,
	Transport: &http.Transport{
		MaxIdleConns:        128,
		MaxIdleConnsPerHost: 64,
		IdleConnTimeout:     90 * time.Second,
	},
}

// ── Handler (I/O-bound fan-out) ──────────────────────────────────────────────
func fanoutHandler(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	n := defaultN
	if raw := q.Get("n"); raw != "" {
		if v, err := strconv.Atoi(raw); err == nil && v > 0 {
			if v > maxN {
				v = maxN
			}
			n = v
		}
	}
	delayMs := defaultDelayMs
	if raw := q.Get("delay_ms"); raw != "" {
		if v, err := strconv.Atoi(raw); err == nil && v >= 0 {
			if v > maxDelayMs {
				v = maxDelayMs
			}
			delayMs = v
		}
	}
	noList := q.Get("no_list") == "true" || q.Get("no_list") == "1"

	url := fmt.Sprintf("%s?delay_ms=%d&size_b=256", backendURL, delayMs)

	start := time.Now()

	statuses := make([]int, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		i := i
		go func() {
			defer wg.Done()
			req, err := http.NewRequestWithContext(r.Context(), http.MethodGet, url, nil)
			if err != nil {
				statuses[i] = 0
				return
			}
			resp, err := httpClient.Do(req)
			if err != nil || resp == nil {
				statuses[i] = 0
				return
			}
			defer resp.Body.Close()
			statuses[i] = resp.StatusCode
		}()
	}
	wg.Wait()

	okCount, errCount := 0, 0
	for _, s := range statuses {
		if s >= 200 && s < 300 {
			okCount++
		} else {
			errCount++
		}
	}

	elapsed := time.Since(start).Microseconds()

	slog.Info("fanout completed",
		"n", n,
		"delay_ms", delayMs,
		"elapsed_us", elapsed,
		"ok_count", okCount,
		"err_count", errCount,
	)

	resp := FanoutResponse{
		Runtime:   "golang-docker",
		N:         n,
		DelayMs:   delayMs,
		OkCount:   okCount,
		ErrCount:  errCount,
		ElapsedUs: elapsed,
	}
	if !noList {
		resp.Responses = statuses
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
	mux.HandleFunc("GET /fanout", fanoutHandler)
	mux.HandleFunc("GET /health", healthHandler)

	addr := ":8080"
	slog.Info("server starting", "addr", addr)

	if err := http.ListenAndServe(addr, mux); err != nil {
		slog.Error("server error", "err", err)
		os.Exit(1)
	}
}
