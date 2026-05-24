# Sequential example model

All four benchmark examples reuse the same four NodePorts:

| Variant         | NodePort |
| --------------- | -------- |
| `wasm-rust`     | 30081    |
| `wasm-tinygo`   | 30082    |
| `docker-rust`   | 30083    |
| `docker-golang` | 30084    |

**Only one example may be active at a time.** If you applied two example
namespaces simultaneously the Kubernetes API server would reject the
second NodePort allocation, and the orchestrator would not know which
pod a request landed on.

This is enforced at every `run_experiment.sh` entry point: before
deploying its own namespace, each orchestrator tears down the other
three sibling namespaces.

## How orchestrators enforce it

For example, `benchmarks/03-http-fanout/run_experiment.sh` runs:

```bash
kubectl delete namespace prime-sieve      --ignore-not-found
kubectl delete namespace memory-bandwidth --ignore-not-found
kubectl delete namespace json-roundtrip   --ignore-not-found
kubectl apply -f k8s/03-http-fanout/
```

The same pattern lives in 01, 02, and 04's orchestrators with the
appropriate sibling list. Re-running an orchestrator is therefore
idempotent: it cleans up whatever was running, re-applies its own
manifests, waits for readiness, runs the benchmark.

## Switching examples manually

If you are not using `run_experiment.sh` (e.g. running ad-hoc curl
checks), do it yourself:

```bash
# Tear down whatever is running
kubectl delete namespace prime-sieve memory-bandwidth http-fanout json-roundtrip \
  --ignore-not-found

# Deploy the example you want
kubectl apply -f k8s/03-http-fanout/namespace.yaml
kubectl apply -f k8s/03-http-fanout/
```

After this, pods take 30–90 s to reach `Running` — see
[deploy.md](deploy.md).

## Namespace names

| Example             | Namespace          |
| ------------------- | ------------------ |
| 01-prime-sieve      | `prime-sieve`      |
| 02-memory-bandwidth | `memory-bandwidth` |
| 03-http-fanout      | `http-fanout`      |
| 04-json-roundtrip   | `json-roundtrip`   |

## Special case: 03 also brings up `io-echo`

The 03 namespace contains five pods, not four: the four variant pods
plus a single-replica `io-echo` backend Deployment that is the outbound
HTTP target for all four fan-out variants. It is created and torn down
together with the 03 namespace. See
[../build/io-echo-backend.md](../build/io-echo-backend.md).
