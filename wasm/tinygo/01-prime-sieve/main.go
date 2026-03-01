// Wasm (WasmEdge) + TinyGo – prime-sieve HTTP service
//
// Build command:
//   tinygo build -o app.wasm -target=wasi -gc=conservative -opt=2 .
//
// Handler code is intentionally identical to docker/golang — same
// net/http types (ResponseWriter, Request, ServeMux), same JSON encoding,
// same query-parameter parsing.  The only difference from docker/golang is
// serveWasmEdge() instead of http.ListenAndServe(): see server.go.

package main

import (
	"encoding/json"
	"fmt"
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
	primes := make([]int, 0, limit/10)
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

	fmt.Fprintf(os.Stderr, "sieve limit=%d count=%d elapsed_us=%d\n",
		limit, len(primes), elapsed)

	resp := SieveResponse{
		Runtime:   "tinygo-wasm",
		Limit:     limit,
		Count:     len(primes),
		ElapsedUs: elapsed,
	}
	if !noList {
		resp.Primes = primes
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		fmt.Fprintf(os.Stderr, "encode error: %v\n", err)
	}
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	fmt.Fprint(w, "ok")
}

// ── Entry point ──────────────────────────────────────────────────────────────
func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/sieve", sieveHandler)
	mux.HandleFunc("/health", healthHandler)

	addr := ":8080"
	fmt.Fprintf(os.Stderr, "tinygo-wasm prime-sieve listening on %s\n", addr)

	if err := serveWasmEdge(addr, mux); err != nil {
		fmt.Fprintf(os.Stderr, "server error: %v\n", err)
		os.Exit(1)
	}
}
