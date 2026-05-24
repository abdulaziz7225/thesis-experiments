# Deploying an experiment

Before deploying, complete [../setup/](../setup/) and
[../build/](../build/) so the cluster is up and all variant images are
pushed.

You can either deploy manually with `kubectl` or let
[run-benchmarks.md](run-benchmarks.md) do it for you (`run_experiment.sh`
handles deployment + teardown automatically). This file covers the
manual path — useful for debugging or running ad-hoc curl probes.

## Required environment

```bash
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
export THESIS_NODE_IP=$(cd ../thesis-infra-setup && terraform output -raw instance_public_ip)
```

## Deploy any single experiment

Only **one example may be active at a time** — they all share NodePorts
30081–30084. See [sequential-example-model.md](sequential-example-model.md)
for why.

```bash
# Tear down whatever is running (idempotent)
kubectl delete namespace prime-sieve memory-bandwidth http-fanout json-roundtrip \
  --ignore-not-found

# Deploy 01-prime-sieve
kubectl apply -f k8s/01-prime-sieve/namespace.yaml
kubectl apply -f k8s/01-prime-sieve/

# OR 02-memory-bandwidth
kubectl apply -f k8s/02-memory-bandwidth/namespace.yaml
kubectl apply -f k8s/02-memory-bandwidth/

# OR 03-http-fanout (I/O-bound — also brings up the io-echo backend)
kubectl apply -f k8s/03-http-fanout/namespace.yaml
kubectl apply -f k8s/03-http-fanout/

# OR 04-json-roundtrip
kubectl apply -f k8s/04-json-roundtrip/namespace.yaml
kubectl apply -f k8s/04-json-roundtrip/
```

Watch pods come up (30–90 s typical, longer on a cold image pull):

```bash
kubectl get pods -n <namespace> -w
```

Expected steady state (example for `prime-sieve`):

```text
NAME                                          READY   STATUS    RESTARTS
prime-sieve-docker-golang-xxx                 1/1     Running   0
prime-sieve-docker-rust-xxx                   1/1     Running   0
prime-sieve-wasm-rust-xxx                     1/1     Running   0
prime-sieve-wasm-tinygo-xxx                   1/1     Running   0
```

For 03 there is one extra pod, `io-echo-xxx`, the in-cluster outbound
HTTP target.

## Quick smoke-test

```bash
IP=${THESIS_NODE_IP}

# Health checks — same on every experiment
curl -s http://${IP}:30081/health          # wasm-rust
curl -s http://${IP}:30082/health          # wasm-tinygo
curl -s http://${IP}:30083/health          # docker-rust
curl -s http://${IP}:30084/health          # docker-golang

# Functional check — 01-prime-sieve
curl -s "http://${IP}:30081/sieve?limit=100&no_list=0" | python3 -m json.tool

# Functional check — 02-memory-bandwidth (after switching examples)
curl -s "http://${IP}:30081/membw?size_kb=64" | python3 -m json.tool

# Functional check — 03-http-fanout (I/O-bound, after switching examples)
# Each variant dispatches n=3 outbound GETs to io-echo (10 ms each):
curl -s "http://${IP}:30081/fanout?n=3&delay_ms=10&no_list=0" | python3 -m json.tool

# Functional check — 04-json-roundtrip (after switching examples)
curl -s -X POST -H 'Content-Type: application/json' \
  -d '[5,1,4,2,3]' \
  "http://${IP}:30081/jsontx?no_list=0" | python3 -m json.tool
```

## Next

To drive the actual benchmark experiments, continue with
[run-benchmarks.md](run-benchmarks.md). For per-experiment workload
specs see [../benchmarks/](../benchmarks/).
