/**
 * k6 load test for the 01-prime-sieve experiment.
 *
 * Usage (single variant):
 *   export THESIS_NODE_IP=<server-ip>
 *
 *   k6 run \
 *     --env BASE_URL=http://$THESIS_NODE_IP:30081 \
 *     --env VUS=50 \
 *     --env DURATION=60s \
 *     --env SIEVE_LIMIT=100000 \
 *     --env NO_LIST=1 \
 *     --summary-export=../../results/01-prime-sieve/wasm-rust_summary.json \
 *     --out json=../../results/01-prime-sieve/wasm-rust_k6.json \
 *     k6-load-test.js
 *
 * Repeat for other variants by changing BASE_URL port and output filenames.
 *
 * Environment variables:
 *   BASE_URL      – full base URL of the variant, e.g. http://1.2.3.4:30081
 *   VUS           – peak number of virtual users (default: 50)
 *   RAMP          – duration to ramp from 1 VU up to VUS (default: 20s)
 *   DURATION      – duration to hold at peak VUS after ramp (default: 60s)
 *   SIEVE_LIMIT   – prime upper bound per request (default: 100000)
 *   NO_LIST       – "1" to omit the primes array from responses (default: 1)
 *
 * Output metrics (available in _summary.json):
 *   http_req_duration   – end-to-end latency (p50, p95, p99)
 *   http_reqs           – total requests / RPS
 *   http_req_failed     – error rate
 *   server_compute_us   – server-side algorithm time extracted from JSON body
 */

import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

// ── Custom metric: server-side algorithm compute time (microseconds) ──────────

const serverComputeUs = new Trend("server_compute_us", false);

// ── Options ───────────────────────────────────────────────────────────────────

export const options = {
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],

  // ramping-vus: start at 1 VU, ramp to VUS over RAMP, hold for DURATION, then cool down.
  // This avoids the "thundering herd" that overwhelms single-threaded sync servers
  // (wasm-rust, wasm-tinygo) while still reaching full load for async servers.
  scenarios: {
    load: {
      executor:        "ramping-vus",
      startVUs:        1,
      stages: [
        { duration: __ENV.RAMP     || "20s", target: parseInt(__ENV.VUS || "50") },
        { duration: __ENV.DURATION || "60s", target: parseInt(__ENV.VUS || "50") },
        { duration: "10s",                   target: 0 },
      ],
      gracefulRampDown: "10s",
    },
  },

  thresholds: {
    // Soft quality gates – informational only, never abort the run.
    http_req_duration: [
      { threshold: "p(95)<5000",  abortOnFail: false },
      { threshold: "p(99)<10000", abortOnFail: false },
    ],
    http_req_failed: [
      { threshold: "rate<0.05", abortOnFail: false },
    ],
  },

  // Tag all requests with the variant derived from the port in BASE_URL so
  // that k6 Cloud / Grafana can filter per-variant without separate runs.
  tags: { variant: __ENV.VARIANT || "unknown" },
};

// ── Default function (executed by every VU on every iteration) ────────────────

export default function () {
  const baseUrl    = __ENV.BASE_URL   || "http://localhost:30081";
  const limit      = __ENV.SIEVE_LIMIT || "100000";
  const noList     = __ENV.NO_LIST    || "1";

  const url = `${baseUrl}/sieve?limit=${limit}&no_list=${noList}`;

  const res = http.get(url, {
    tags: { endpoint: "/sieve" },
  });

  const ok = check(res, {
    "status 200": (r) => r.status === 200,
  });

  if (ok) {
    try {
      const body = JSON.parse(res.body);
      if (body.elapsed_us !== undefined) {
        serverComputeUs.add(body.elapsed_us);
      }
    } catch (_) {
      // non-JSON or missing field – skip silently
    }
  }
}

// ── Setup: verify the variant is healthy before starting the load ─────────────

export function setup() {
  const baseUrl = __ENV.BASE_URL || "http://localhost:30081";
  const res = http.get(`${baseUrl}/health`);
  if (res.status !== 200) {
    throw new Error(
      `Health check failed for ${baseUrl} (HTTP ${res.status}). ` +
      "Ensure the variant is running before starting the load test."
    );
  }
  console.log(`Health check OK: ${baseUrl}`);
}
