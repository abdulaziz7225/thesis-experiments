// TinyGo + Spin (SpinKube / wasip1) – prime-sieve HTTP component
//
// Build:  tinygo build -target=wasip1 -gc=conservative -opt=2 -o app.wasm .
// Push:   spin registry push docker.io/abdulaziz7225/prime-sieve-wasm-tinygo:latest
// Deploy: kubectl apply -f k8s/01-prime-sieve/wasm-tinygo.yaml
//
// Why wasip1 (not wasip2): TinyGo's wasip2 target compiles to a WASI CLI command
// (exports wasi:cli/run), NOT a wasi:http/proxy component. Spin requires one of:
//   wasi:http/incoming-handler@0.2.*, or fermyon:spin/inbound-http.
// The Fermyon Go SDK (wasip1 + CGo) exports fermyon:spin/inbound-http, which Spin
// accepts. wasip2 without the SDK is not a valid Spin HTTP component.
//
// runtime field in JSON: "wasm-tinygo"
//
// Handler code is identical to docker/golang variant —
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

	spinhttp "github.com/spinframework/spin-go-sdk/v2/http"
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
// spinhttp.Handle() registers the top-level dispatcher. Spin calls
// spin_http_handle_http_request (exported by the Fermyon SDK's C layer) on
// each HTTP request and routes it here.
func init() {
	spinhttp.Handle(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/sieve":
			sieveHandler(w, r)
		case "/health":
			healthHandler(w, r)
		default:
			http.NotFound(w, r)
		}
	})
}

// main must be present but empty — Spin calls the registered handler via CGo export.
func main() {}
