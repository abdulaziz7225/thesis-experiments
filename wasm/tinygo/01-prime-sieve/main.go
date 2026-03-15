// TinyGo + Spin (SpinKube / WASI P2) – prime-sieve HTTP component
//
// Build:  tinygo build -target=wasip2 -gc=conservative -opt=2 -o app.wasm .
// Push:   spin registry push docker.io/abdulaziz7225/prime-sieve-wasm-tinygo:latest
// Deploy: kubectl apply -f k8s/01-prime-sieve/wasm-tinygo.yaml
//
// Key differences from wasm/wasmedge/tinygo/01-prime-sieve (WASI P1 archive):
//   - Runtime:  Wasmtime/Cranelift (via Spin)  vs  WasmEdge/LLVM
//   - WASI:     Preview 2 (Component Model)    vs  Preview 1 (snapshot_preview1)
//   - HTTP:     spinhttp.Handle() + net/http    vs  serveWasmEdge() custom TCP loop
//   - server.go is ELIMINATED — no //go:wasmimport sock_open/bind/listen needed
//   - TinyGo wasip2 target handles wasi:http bindings automatically via Spin SDK
//   - runtime field in JSON: "wasm-tinygo"
//
// Handler code is identical to wasm/tinygo and docker/golang variants —
// same net/http types (ResponseWriter, Request), same JSON encoding,
// same query-parameter parsing.

package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"time"
)

// ── Response ─────────────────────────────────────────────────────────────────
type SieveResponse struct {
	Runtime   string `json:"runtime"`
	Limit     int    `json:"limit"`
	Count     int    `json:"count"`
	Primes    []int  `json:"primes,omitempty"`
	ElapsedUs int64  `json:"elapsed_us"`
}

// ── Algorithm ─────────────────────────────────────────────────────────────────
// Identical to docker/golang and wasm/tinygo variants — algorithm is not the variable.
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

// ── Handlers ─────────────────────────────────────────────────────────────────
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
		Runtime:   "wasm-tinygo",
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
}

// ── Entry point ───────────────────────────────────────────────────────────────
// TinyGo wasip2 automatically exports wasi:http/incoming-handler using the
// default http.ServeMux. No Spin SDK or spinhttp.Handle() call needed.
func init() {
	http.HandleFunc("/sieve", sieveHandler)
	http.HandleFunc("/health", healthHandler)
}

// main must be present but is empty — the wasip2 runtime dispatches HTTP requests.
func main() {}
