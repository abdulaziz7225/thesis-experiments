// TinyGo + Spin (SpinKube / WASI P1) – JSON round-trip HTTP component.
//
// Build:  tinygo build -target=wasip1 -gc=conservative -opt=2 -o app.wasm .
// Push:   spin registry push docker.io/abdulaziz7225/json-roundtrip-wasm-tinygo:latest
// Deploy: kubectl apply -f k8s/04-json-roundtrip/wasm-tinygo.yaml
//
// Why wasip1 (not wasip2): see 02-memory-bandwidth/main.go comment.
//
// Workload: parse a POSTed JSON array of integers, sort descending, compute
// count/sum/min/max/mean/median/stdev, re-serialise the response. Exercises
// encoding/json on the hot path, allocator under small irregular allocations,
// and the host->guest HTTP-body copy across the WASI P1 boundary.

package main

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"sort"
	"time"

	spinhttp "github.com/spinframework/spin-go-sdk/v2/http"
)

// ── Response ─────────────────────────────────────────────────────────────────
type JsonTxResponse struct {
	Runtime   string  `json:"runtime"`
	N         int     `json:"n"`
	Count     int     `json:"count"`
	Sum       int64   `json:"sum"`
	Min       int64   `json:"min"`
	Max       int64   `json:"max"`
	Mean      float64 `json:"mean"`
	Median    int64   `json:"median"`
	Stdev     float64 `json:"stdev"`
	ElapsedUs int64   `json:"elapsed_us"`
	Sorted    []int64 `json:"sorted,omitempty"`
}

func computeStats(sortedDesc []int64) (sum, min, max, median int64, mean, stdev float64) {
	n := len(sortedDesc)
	if n == 0 {
		return
	}
	for _, v := range sortedDesc {
		sum += v
	}
	max = sortedDesc[0]
	min = sortedDesc[n-1]
	mean = float64(sum) / float64(n)
	// Median definition: descending-sort, then arr[(n-1)/2] (mid-low for even N).
	// Same formula across all four variants to keep results comparable.
	median = sortedDesc[(n-1)/2]
	var variance float64
	for _, v := range sortedDesc {
		d := float64(v) - mean
		variance += d * d
	}
	variance /= float64(n)
	stdev = math.Sqrt(variance)
	return
}

func jsonTxHandler(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	noList := q.Get("no_list") == "true" || q.Get("no_list") == "1"

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "could not read body", http.StatusBadRequest)
		return
	}

	start := time.Now()

	var arr []int64
	if err := json.Unmarshal(body, &arr); err != nil {
		http.Error(w, "expected JSON array of integers", http.StatusBadRequest)
		return
	}

	sort.Slice(arr, func(i, j int) bool { return arr[i] > arr[j] })
	sum, min, max, median, mean, stdev := computeStats(arr)
	count := len(arr)

	elapsed := time.Since(start).Microseconds()
	fmt.Fprintf(os.Stderr, "jsontx count=%d elapsed_us=%d\n", count, elapsed)

	resp := JsonTxResponse{
		Runtime:   "wasm-tinygo",
		N:         count,
		Count:     count,
		Sum:       sum,
		Min:       min,
		Max:       max,
		Mean:      mean,
		Median:    median,
		Stdev:     stdev,
		ElapsedUs: elapsed,
	}
	if !noList {
		resp.Sorted = arr
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
func init() {
	spinhttp.Handle(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/health" && r.Method == http.MethodGet:
			healthHandler(w, r)
		case r.URL.Path == "/jsontx" && r.Method == http.MethodPost:
			jsonTxHandler(w, r)
		default:
			http.NotFound(w, r)
		}
	})
}

func main() {}
