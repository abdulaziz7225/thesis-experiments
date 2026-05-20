/**
 * k6 load test for the 03-http-fanout (I/O-bound) experiment.
 *
 * Workload class: I/O-bound. Each variant forwards a single inbound request
 * into N concurrent outbound HTTP GETs to the in-cluster io-echo backend,
 * which sleeps for delay_ms before responding. Throughput is therefore gated
 * by the I/O-wait floor, not by CPU work — this is the I/O-bound counterpart
 * to 01-prime-sieve (CPU-bound) and 02-memory-bandwidth (memory-bound).
 *
 * Usage (single variant):
 *   export THESIS_NODE_IP=<server-ip>
 *
 *   k6 run \
 *     --env BASE_URL=http://$THESIS_NODE_IP:30081 \
 *     --env VARIANT=wasm-rust \
 *     --env VUS=50 \
 *     --env DURATION=60s \
 *     --env N=5 \
 *     --env DELAY_MS=50 \
 *     --env NO_LIST=1 \
 *     --summary-export=../../results/03-http-fanout/wasm-rust_summary.json \
 *     --out json=../../results/03-http-fanout/wasm-rust_k6.json \
 *     k6-load-test.js
 *
 * Environment variables:
 *   BASE_URL   – full base URL of the variant, e.g. http://1.2.3.4:30081
 *   VARIANT    – variant name for tagging (e.g. "wasm-rust")
 *   VUS        – peak number of virtual users (default: 50)
 *   RAMP       – duration to ramp from 1 VU up to VUS (default: 20s)
 *   DURATION   – duration to hold at peak VUS (default: 60s)
 *   N          – outbound fan-out width per inbound request (default: 5, max 20)
 *   DELAY_MS   – backend sleep per outbound call (default: 50, max 1000)
 *   NO_LIST    – "1" to omit per-response status array (default: 1, removes a
 *                serialization confound)
 *
 * Output metrics:
 *   http_req_duration – end-to-end latency (p50, p95, p99)
 *   http_reqs         – total requests / RPS
 *   http_req_failed   – error rate
 *   server_fanout_us  – server-side fan-out time extracted from JSON body
 *                       (first-outbound-dispatched → all-outbounds-complete)
 */

import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const serverFanoutUs = new Trend("server_fanout_us", false);

export const options = {
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],

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
    http_req_duration: [
      { threshold: "p(95)<5000",  abortOnFail: false },
      { threshold: "p(99)<10000", abortOnFail: false },
    ],
    http_req_failed: [
      { threshold: "rate<0.05", abortOnFail: false },
    ],
  },

  tags: { variant: __ENV.VARIANT || "unknown", workload: "io-bound" },
};

export default function () {
  const baseUrl = __ENV.BASE_URL || "http://localhost:30081";
  const n       = __ENV.N        || "5";
  const delayMs = __ENV.DELAY_MS || "50";
  const noList  = __ENV.NO_LIST  || "1";

  const url = `${baseUrl}/fanout?n=${n}&delay_ms=${delayMs}&no_list=${noList}`;

  const res = http.get(url, {
    tags: { endpoint: "/fanout" },
  });

  const ok = check(res, {
    "status 200": (r) => r.status === 200,
  });

  if (ok) {
    try {
      const body = JSON.parse(res.body);
      if (body.elapsed_us !== undefined) {
        serverFanoutUs.add(body.elapsed_us);
      }
    } catch (_) {
      // non-JSON or missing field — skip
    }
  }
}

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
