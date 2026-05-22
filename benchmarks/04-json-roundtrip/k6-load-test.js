/**
 * k6 load test for the 04-json-roundtrip experiment.
 *
 * Workload: POST /jsontx?n=N&no_list=1 with a JSON array of N integers in
 * the request body. The server parses the array, sorts descending, computes
 * count/sum/min/max/mean/median/stdev, re-serialises the response.
 *
 * The N value is sweeped at the harness level (see run_experiment.sh):
 * one k6 invocation per N in [100, 1000, 10000, 100000] per variant.
 *
 * Usage (single variant, single N):
 *   export THESIS_NODE_IP=<server-ip>
 *
 *   k6 run \
 *     --env BASE_URL=http://$THESIS_NODE_IP:30081 \
 *     --env VARIANT=wasm-rust \
 *     --env N=1000 \
 *     --env VUS=20 \
 *     --env DURATION=30s \
 *     --env NO_LIST=1 \
 *     --summary-export=../../results/04-json-roundtrip/limited/wasm-rust_n1000_summary.json \
 *     --out json=../../results/04-json-roundtrip/limited/wasm-rust_n1000_k6.json \
 *     k6-load-test.js
 *
 * Environment variables:
 *   BASE_URL   – full base URL of the variant, e.g. http://1.2.3.4:30081
 *   VARIANT    – variant name for tagging (e.g. "wasm-rust")
 *   N          – array length per request (default: 1000)
 *   VUS        – peak number of virtual users (default: 20)
 *   RAMP       – duration to ramp from 1 VU up to VUS (default: 10s)
 *   DURATION   – duration to hold at peak VUS (default: 30s)
 *   NO_LIST    – "1" to omit the sorted array from the response body (default: 1)
 *
 * Output metrics:
 *   http_req_duration – end-to-end latency (p50, p95, p99)
 *   http_reqs         – total requests / RPS
 *   http_req_failed   – error rate
 *   server_jsontx_us  – server-side parse+sort+stats+reserialise time
 */

import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const serverJsonTxUs = new Trend("server_jsontx_us", false);

const N = parseInt(__ENV.N || "1000");

// Build the request body once per VU (k6 V8 context) so request-time work
// is dominated by the server-side parse + transform, not by k6 JSON-stringify.
function buildPayload(n) {
  const arr = new Array(n);
  for (let i = 0; i < n; i++) {
    // Deterministic pseudo-random sequence so payloads are not trivially sortable.
    arr[i] = ((i + 1) * 2654435761) >>> 0;
  }
  return JSON.stringify(arr);
}

const PAYLOAD = buildPayload(N);
const PAYLOAD_KB = Math.round(PAYLOAD.length / 1024);

export const options = {
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],

  scenarios: {
    load: {
      executor:        "ramping-vus",
      startVUs:        1,
      stages: [
        { duration: __ENV.RAMP     || "10s", target: parseInt(__ENV.VUS || "20") },
        { duration: __ENV.DURATION || "30s", target: parseInt(__ENV.VUS || "20") },
        { duration: "5s",                    target: 0 },
      ],
      gracefulRampDown: "10s",
    },
  },

  thresholds: {
    http_req_duration: [
      { threshold: "p(95)<10000", abortOnFail: false },
      { threshold: "p(99)<20000", abortOnFail: false },
    ],
    http_req_failed: [
      { threshold: "rate<0.05", abortOnFail: false },
    ],
  },

  tags: {
    variant: __ENV.VARIANT || "unknown",
    n:       String(N),
  },
};

const PARAMS = {
  headers: { "Content-Type": "application/json" },
  tags:    { endpoint: "/jsontx" },
};

export default function () {
  const baseUrl = __ENV.BASE_URL || "http://localhost:30081";
  const noList  = __ENV.NO_LIST  || "1";

  const url = `${baseUrl}/jsontx?n=${N}&no_list=${noList}`;
  const res = http.post(url, PAYLOAD, PARAMS);

  const ok = check(res, {
    "status 200": (r) => r.status === 200,
  });

  if (ok) {
    try {
      const body = JSON.parse(res.body);
      if (body.elapsed_us !== undefined) {
        serverJsonTxUs.add(body.elapsed_us);
      }
    } catch (_) {
      // skip
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
  console.log(`Health check OK: ${baseUrl}  (N=${N}, payload ≈ ${PAYLOAD_KB} KB)`);
}
