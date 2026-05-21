package main

import (
	"encoding/json"
	"log/slog"
	"math"
	"net/http"
	"os"
	"sort"
	"time"
)

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

	// Allow request bodies up to ~16 MiB (well above a 100k-int JSON array).
	r.Body = http.MaxBytesReader(w, r.Body, 16<<20)

	var arr []int64
	if err := json.NewDecoder(r.Body).Decode(&arr); err != nil {
		http.Error(w, "expected JSON array of integers", http.StatusBadRequest)
		return
	}

	start := time.Now()

	sort.Slice(arr, func(i, j int) bool { return arr[i] > arr[j] })
	sum, min, max, median, mean, stdev := computeStats(arr)
	count := len(arr)

	elapsed := time.Since(start).Microseconds()

	slog.Info("jsontx completed",
		"count", count,
		"elapsed_us", elapsed,
	)

	resp := JsonTxResponse{
		Runtime:   "golang-docker",
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
		slog.Error("encode error", "err", err)
	}
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(logger)

	mux := http.NewServeMux()
	mux.HandleFunc("POST /jsontx", jsonTxHandler)
	mux.HandleFunc("GET /health", healthHandler)

	addr := ":8080"
	slog.Info("server starting", "addr", addr)

	if err := http.ListenAndServe(addr, mux); err != nil {
		slog.Error("server error", "err", err)
		os.Exit(1)
	}
}
