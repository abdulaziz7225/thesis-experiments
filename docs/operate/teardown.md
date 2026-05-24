# Tear down

Two levels: remove the experiment workloads only (keep the cluster
running for later experiments), or destroy the whole Hetzner VM.

## Remove experiment workloads only

Idempotent and safe — re-deploys cleanly afterwards.

```bash
kubectl delete namespace prime-sieve memory-bandwidth http-fanout json-roundtrip \
  --ignore-not-found
```

Each orchestrator (`./benchmarks/<example>/run_experiment.sh`) does this
automatically for sibling examples on its way in — see
[sequential-example-model.md](sequential-example-model.md).

## Destroy the VM

When you are done with the cluster entirely:

```bash
cd ../thesis-infra-setup
make teardown
```

This calls `terraform destroy`, which removes the Hetzner Cloud VM and
its network. You'll need to re-run the full
[../setup/02-infrastructure.md](../setup/02-infrastructure.md) flow to
get a cluster back.

## Local cleanup

The benchmark output under `results/` is git-ignored (the orchestrators
write fresh files on every run). If you want to start with a clean slate:

```bash
rm -rf results/0*-*/{limited,unlimited}/{charts,*_summary.json,*_k6.json}
rm -f  results/0*-*/{cold,warm}_start.json
rm -f  results/0*-*/resource_metrics.json
rm -f  results/0*-*/image_sizes.json
rm -f  results/0*-*/binary_sizes.json
```

The Python venv at `.venv/` can also be removed safely:

```bash
deactivate 2>/dev/null || true
rm -rf .venv/
```

`docker image prune` and `docker rmi <ref>` clean up local image copies
if you need disk space back.
