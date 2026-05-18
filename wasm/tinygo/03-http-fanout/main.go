// TinyGo + Spin (SpinKube / WASI P1) – HTTP fan-out HTTP component (I/O-bound experiment).
//
// Build:  tinygo build -target=wasip1 -gc=conservative -opt=2 -o app.wasm .
// Push:   spin registry push docker.io/abdulaziz7225/http-fanout-wasm-tinygo:latest
// Deploy: kubectl apply -f k8s/03-http-fanout/wasm-tinygo.yaml
//
// Why wasip1 (not wasip2): TinyGo's wasip2 target hardwires the wasi:cli/command
// world and cannot export wasi:http/incoming-handler. The Spin Go SDK
// (spinframework/spin-go-sdk/v2) uses CGo to export fermyon:spin/inbound-http,
// which Spin accepts as a valid HTTP trigger interface.
//
// Workload (I/O-bound): on each inbound request, dispatch N outbound HTTP GETs
// to the in-cluster `io-echo` backend. The backend sleeps for `delay_ms`
// before responding, so the handler is dominated by outbound I/O wait rather
// than CPU work.
//
// Concurrency note: the outbound GETs are issued SEQUENTIALLY in this variant.
// TinyGo's wasip1 runtime panics on `sync.WaitGroup.Wait()` (nil pointer
// dereference in the goroutine scheduler), and `spinhttp.Send` is itself
// blocking per call. The Rust + WASI P2 variant retains real async fan-out
// via `futures::join_all` — the cross-variant comparison of "concurrent
// outbound HTTP availability on WASI P2 vs WASI P1" is itself the
// thesis-relevant signal.

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

	// TinyGo + WASI P1 outbound HTTP is single-threaded by construction
	// (cooperative Asyncify scheduler, blocking spinhttp.Send) and sync.WaitGroup
	// trips a nil-pointer panic in the TinyGo wasip1 runtime, so the outbound
	// GETs are issued sequentially. This is honest about the platform's
	// I/O concurrency story — the Rust + WASI P2 variant retains real async
	// fan-out via futures::join_all, and the comparison is the thesis-relevant
	// signal.
	statuses := make([]int, n)
	for i := 0; i < n; i++ {
		req, err := http.NewRequest(http.MethodGet, url, nil)
		if err != nil {
			statuses[i] = 0
			continue
		}
		resp, err := spinhttp.Send(req)
		if err != nil || resp == nil {
			statuses[i] = 0
			continue
		}
		statuses[i] = resp.StatusCode
		resp.Body.Close()
	}

	okCount, errCount := 0, 0
	for _, s := range statuses {
		if s >= 200 && s < 300 {
			okCount++
		} else {
			errCount++
		}
	}

	elapsed := time.Since(start).Microseconds()
	fmt.Fprintf(os.Stderr, "fanout n=%d delay_ms=%d elapsed_us=%d ok=%d err=%d\n",
		n, delayMs, elapsed, okCount, errCount)

	resp := FanoutResponse{
		Runtime:   "wasm-tinygo",
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
		fmt.Fprintf(os.Stderr, "encode error: %v\n", err)
	}
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
}

// ── Entry point ───────────────────────────────────────────────────────────────
// spinhttp.Handle() registers the top-level dispatcher. Spin calls the C-export
// shim on each HTTP request and routes it here.
func init() {
	spinhttp.Handle(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/fanout":
			fanoutHandler(w, r)
		case "/health":
			healthHandler(w, r)
		default:
			http.NotFound(w, r)
		}
	})
}

// main must be present but empty — Spin calls the registered handler via CGo export.
func main() {}
