# Cluster infrastructure

The benchmark workloads run on a **single-node Kubernetes cluster on a
Hetzner Cloud `ccx23` VM** (4 vCPU, 16 GB RAM, upstream Kubernetes 1.34 via
kubeadm). The Terraform + cloud-init that provisions the VM, installs
kubeadm + Flannel + the containerd-shim-spin shim, and deploys the
SpinOperator + cert-manager + Prometheus + Grafana stack all live in a
**separate GitHub repository**:

> [github.com/abdulaziz7225/thesis-infra-setup](https://github.com/abdulaziz7225/thesis-infra-setup)

## Bring the cluster up

```bash
cd ../thesis-infra-setup

make up            # 1. Provision Hetzner server + run cloud-init (kubeadm + containerd-shim-spin-v2)
make configure     # 2. Wait for kubeadm, fetch kubeconfig → hetzner-thesis.yaml
make label         # 3. Label node with SpinKube capability (runtime.spin.fermyon.com/v2=true)
make deploy        # 4. Deploy cert-manager, SpinOperator, Prometheus, Grafana, RuntimeClass
make test          # 5. Smoke-test: run a SpinApp pod and verify HTTP 200
make info          # 6. Print access URLs and credentials

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
