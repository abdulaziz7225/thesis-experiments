# Build and push — io-echo backend (03-http-fanout only)

The 03 HTTP fan-out experiment has each variant dispatch N **concurrent
outbound HTTP GETs** to a small in-cluster backend. That backend — the
`io-echo` Deployment — sleeps for a configurable `delay_ms` before
responding, holding the per-outbound latency floor stable so the measured
inbound-side throughput / latency is attributable to runtime + language
overhead rather than backend noise.

`io-echo` is **not** part of the four-variant comparison matrix. It is
the I/O target. Source lives at `backend/io-echo/`.

Build and push it **once**; it is reused by all four 03 variants.

```bash
export DOCKER_USER=<YOUR_DOCKERHUB_USERNAME>

docker build -t docker.io/${DOCKER_USER}/io-echo-backend:latest backend/io-echo/
docker push  docker.io/${DOCKER_USER}/io-echo-backend:latest
```

The image follows the same scratch + `-trimpath` + `-ldflags="-s -w"`
pattern as the docker-golang variants (see
[docker-variants.md](docker-variants.md)).

## Deployment shape

The Kubernetes manifest at `k8s/03-http-fanout/io-echo.yaml` exposes the
backend as a **ClusterIP-only** Service (no NodePort) at
`http://io-echo.http-fanout.svc.cluster.local:80`. The four 03 variants
resolve it via in-cluster DNS.

The two Spin variants additionally restrict outbound HTTP to just this
host via `allowed_outbound_hosts` in their `spin.toml` files — a
deny-by-default posture that matches Spin's idiomatic capability model.

## Tuning the I/O floor

`io-echo` accepts two query parameters that the 03 variants pass through:

- `delay_ms` — server-side sleep before responding (default 50, max 1000)
- `size_b` — bytes of payload in the response body (default 256, max 65536)

The harness defaults (`./benchmarks/03-http-fanout/run_experiment.sh
--n 5 --delay-ms 50`) issue 5 concurrent outbound GETs at 50 ms each —
the per-request floor is therefore ~50 ms (concurrent) or ~250 ms
(sequential, the TinyGo variant).
