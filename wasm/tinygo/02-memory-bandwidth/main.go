// TinyGo + Spin (SpinKube / wasip1) – memory-bandwidth HTTP component
//
// Build:  tinygo build -target=wasip1 -gc=conservative -opt=2 -o app.wasm .
// Push:   spin registry push docker.io/abdulaziz7225/memory-bandwidth-wasm-tinygo:latest
// Deploy: kubectl apply -f k8s/02-memory-bandwidth/wasm-tinygo.yaml
//
// Why wasip1 (not wasip2): TinyGo's wasip2 target hardwires the wasi:cli/command
// world and cannot export wasi:http/incoming-handler. The Spin Go SDK
// (spinframework/spin-go-sdk/v2) uses CGo to export fermyon:spin/inbound-http,
// which Spin accepts as a valid HTTP trigger interface. wasip2 without the SDK
// is not a valid Spin HTTP component.
//
// Workload: allocate a byte buffer of configurable size (default 64 KB),
// fill with deterministic pattern, compute SHA-256 hash, return result.
// Uses in-memory allocation (no filesystem) for consistency across all variants.

package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"time"

	spinhttp "github.com/spinframework/spin-go-sdk/v2/http"
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
	fmt.Fprintf(os.Stderr, "membw size_kb=%d elapsed_us=%d\n", sizeKb, elapsed)

	resp := MemBwResponse{
		Runtime:   "wasm-tinygo",
		SizeKb:    sizeKb,
		Sha256:    hashStr,
		ElapsedUs: elapsed,
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
		case "/membw":
			memBwHandler(w, r)
		case "/health":
			healthHandler(w, r)
		default:
			http.NotFound(w, r)
		}
	})
}

// main must be present but empty — Spin calls the registered handler via CGo export.
func main() {}
