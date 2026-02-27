// TinyGo + WASM (WasmEdge) – prime-sieve HTTP service
//
// Build command:
//   tinygo build -o app.wasm -target=wasip1 -gc=conservative -opt=2 .
//
// Runtime note:
//   TinyGo's net/http server relies on WASI socket syscalls (sock_accept,
//   sock_listen, …) which WasmEdge provides as an extension to WASI P1.
//   Make sure the WasmEdge runtime is started with socket support enabled
//   (default in WasmEdge ≥ 0.11 and runwasi containerd-shim-wasmedge ≥ 0.4).

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
// sieve returns every prime p where 2 ≤ p ≤ limit.
func sieve(limit int) []int {
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

	primes := make([]int, 0)
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

	start   := time.Now()
	primes  := sieve(limit)
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
	fmt.Fprint(w, "ok")
}

// ── Entry point ──────────────────────────────────────────────────────────────
func main() {
	http.HandleFunc("/sieve",  sieveHandler)
	http.HandleFunc("/health", healthHandler)

	addr := ":8080"
	fmt.Fprintf(os.Stderr, "tinygo-wasm prime-sieve listening on %s\n", addr)

	if err := http.ListenAndServe(addr, nil); err != nil {
		fmt.Fprintf(os.Stderr, "server error: %v\n", err)
		os.Exit(1)
	}
}
