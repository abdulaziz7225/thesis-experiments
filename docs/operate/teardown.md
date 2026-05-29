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
