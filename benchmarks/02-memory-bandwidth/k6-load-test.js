/**
 * k6 load test for the 02-memory-bandwidth experiment.
 *
 * Usage (single variant):
 *   export THESIS_NODE_IP=<server-ip>
 *
 *   k6 run \
 *     --env BASE_URL=http://$THESIS_NODE_IP:30081 \
 *     --env VARIANT=wasm-rust \
 *     --env VUS=50 \
 *     --env DURATION=60s \
 *     --env SIZE_KB=64 \
 *     --env NO_HASH=0 \
 *     --summary-export=../../results/02-memory-bandwidth/wasm-rust_summary.json \
 *     --out json=../../results/02-memory-bandwidth/wasm-rust_k6.json \
 *     k6-load-test.js
 *
 * Environment variables:
 *   BASE_URL   – full base URL of the variant, e.g. http://1.2.3.4:30081
 *   VARIANT    – variant name for tagging (e.g. "wasm-rust")
 *   VUS        – peak number of virtual users (default: 50)
 *   RAMP       – duration to ramp from 1 VU up to VUS (default: 20s)
 *   DURATION   – duration to hold at peak VUS (default: 60s)
 *   SIZE_KB    – buffer size in KB per request (default: 64)
 *   NO_HASH    – "1" to skip SHA-256 hashing (default: 0)
 *
 * Output metrics:
 *   http_req_duration – end-to-end latency (p50, p95, p99)
 *   http_reqs         – total requests / RPS
 *   http_req_failed   – error rate
 *   server_membw_us      – server-side allocation+hash time extracted from JSON body
 */

import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const serverMembwUs = new Trend("server_membw_us", false);

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

  tags: { variant: __ENV.VARIANT || "unknown" },
};

export default function () {
  const baseUrl = __ENV.BASE_URL || "http://localhost:30081";
  const sizeKb  = __ENV.SIZE_KB  || "64";
  const noHash  = __ENV.NO_HASH  || "0";

  const url = `${baseUrl}/membw?size_kb=${sizeKb}&no_hash=${noHash}`;

  const res = http.get(url, {
    tags: { endpoint: "/membw" },
  });

  const ok = check(res, {
    "status 200": (r) => r.status === 200,
  });

  if (ok) {
    try {
      const body = JSON.parse(res.body);
      if (body.elapsed_us !== undefined) {
        serverMembwUs.add(body.elapsed_us);
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
