# Cluster infrastructure

The benchmark workloads run on a **single-node Kubernetes cluster on a
Hetzner Cloud `ccx23` VM** (4 vCPU, 16 GB RAM, upstream Kubernetes 1.34 via
kubeadm). The Terraform + cloud-init that provisions the VM, installs
kubeadm + Flannel + the containerd-shim-spin shim, and deploys the
SpinOperator + cert-manager + Prometheus + Grafana stack all live in a
**separate GitHub repository**:

> [github.com/abdulaziz7225/thesis-infra-setup](https://github.com/abdulaziz7225/thesis-infra-setup)

The doc commands below reference it via the relative path
`../thesis-infra-setup/`, which is correct **only if you cloned both
repos as siblings** per
[01-prerequisites.md § Clone the two source repositories as siblings](01-prerequisites.md#clone-the-two-source-repositories-as-siblings).

Complete the steps below **before** moving on to
[../build/](../build/) or [../operate/deploy.md](../operate/deploy.md).
[01-prerequisites.md](01-prerequisites.md) covers the workstation-side
tooling you need first.

## Bring the cluster up

```bash
cd ../thesis-infra-setup

# 1. Provision the Hetzner VM (Terraform + cloud-init: kubeadm + SpinKube)
make up

# 2. Wait for cloud-init and fetch kubeconfig (~5-8 min)
make configure

# 3. Label the node so the SpinKube RuntimeClass can schedule pods
make label

# 4. Deploy cert-manager, SpinOperator, Prometheus, Grafana
make deploy

# 5. Smoke-test: verifies Spin/Wasmtime can run a SpinApp at all
make test
# Expected: HTTP 200 from the hello-spin SpinApp

cd ../thesis-experiments
```

After `make configure`, you'll have `../thesis-infra-setup/hetzner-thesis.yaml`
on disk. Export `KUBECONFIG` and `THESIS_NODE_IP`:

```bash
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
export THESIS_NODE_IP=$(cd ../thesis-infra-setup && terraform output -raw instance_public_ip)
```

These two variables are referenced by **every** orchestrator script.

## What's running on the node after `make deploy`

- `kube-apiserver`, `etcd`, `kube-scheduler`, `kube-controller-manager`,
  `kubelet` (the single-node control plane)
- Flannel CNI
- containerd with the `runc` and `containerd-shim-spin-v2` runtimes
- `cert-manager` (prerequisite for the SpinOperator webhooks)
- `SpinOperator` (manages `SpinApp` CRDs)
- `kube-prometheus-stack` (Prometheus + Grafana + node-exporter +
  kube-state-metrics)

The benchmark namespaces (`prime-sieve`, `memory-bandwidth`, `http-fanout`,
`json-roundtrip`) are created **per experiment** by the orchestrator
scripts — see
[../operate/sequential-example-model.md](../operate/sequential-example-model.md).

## Observability endpoints

| Service    | URL                             | Credentials                |
| ---------- | ------------------------------- | -------------------------- |
| Grafana    | `http://<THESIS_NODE_IP>:32000` | `admin` / `thesis-grafana` |
| Prometheus | `http://<THESIS_NODE_IP>:32090` | —                          |

See [../operate/observability.md](../operate/observability.md) for useful
PromQL queries and dashboard tips.

## Recovering from cluster collapse

If the VM becomes unreachable mid-experiment (kube-apiserver / NodePorts /
SSH all time out), see
[../reference/troubleshooting.md](../reference/troubleshooting.md) for
the Hetzner reboot flow.

## Tearing the cluster down

When you're done, see [../operate/teardown.md](../operate/teardown.md).
