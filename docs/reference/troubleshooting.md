# Troubleshooting

Common failure modes encountered when running the experiments, and how
to recover.

## Cluster collapse during a load test

**Symptoms**: mid-experiment, every NodePort times out
(`curl http://${THESIS_NODE_IP}:30081/health` hangs), kube-apiserver
on `${THESIS_NODE_IP}:6443` is unreachable, even SSH on port 22 times
out. The Prometheus query inside `run_experiment.sh` raises a
`ConnectTimeoutError` and the script aborts.

**Root cause**: the Hetzner ccx23 has 4 vCPU shared between the control
plane (kube-apiserver, etcd, kubelet), the observability stack
(Prometheus, kube-state-metrics), the SpinOperator, _and_ the variant
pods. A high-amplification workload like 03 (each inbound request
generates 5 concurrent outbound requests to `io-echo`) can saturate
either kernel resources (conntrack table, ephemeral ports), CPU, or
both — and take the apiserver down with it.

**Recovery flow**:

```bash
# 1. Is the VM itself up? (Hetzner Cloud API — not via Kubernetes)
cd ../thesis-infra-setup
hcloud server list

# 2a. If "running" but unreachable → soft reboot
hcloud server reboot <server-name>
# Wait 60-90 s, then re-test
timeout 5 curl http://${THESIS_NODE_IP}:32090/-/healthy

# 2b. If "off" → power on
hcloud server poweron <server-name>

# 2c. If a soft reboot doesn't recover within ~3 min, the kernel is
# wedged. Use the Hetzner Console to force-reset.
```

Once the VM is back, the cluster needs 2-5 minutes for kube-apiserver,
etcd, and SpinOperator to reconverge. Verify:

```bash
timeout 10 kubectl --kubeconfig $KUBECONFIG get nodes
timeout 10 kubectl --kubeconfig $KUBECONFIG -n <namespace> get pods
```

**Prevention**: for 03 specifically, lower the default VU count
(`--users 20` instead of 50) and bump `io-echo` replicas in
`k8s/03-http-fanout/io-echo.yaml` to give the backend more headroom.
The amplification factor is `N` outbound per inbound — at default
`--n 5` and 50 VUs, a 569 RPS docker-rust run pushes ~2 845 RPS at
`io-echo`.

## Pod stuck in `ImagePullBackOff`

**Symptoms**: `kubectl get pods` shows `0/1 ImagePullBackOff` for one
or more variants.

**Common causes**:

1. The variant image was not pushed. Re-run the relevant block in
   [../build/docker-variants.md](../build/docker-variants.md) or
   [../build/wasm-variants.md](../build/wasm-variants.md).
2. The image reference in the K8s manifest uses a different Docker Hub
   username. The committed manifests reference
   `docker.io/abdulaziz7225/<image>:latest`. If you push under a
   different account, search-and-replace the username in
   `k8s/<example>/*.yaml` before applying.
3. **Spin variants pushed with `docker push` instead of `spin registry push`**.
   The SpinOperator admission webhook rejects images that lack the
   `application/vnd.fermyon.spin.manifest.v2+json` media type. Re-push
   with the Spin CLI.

## Wasm-tinygo build fails with `requires go version 1.19 through 1.25`

**Symptoms**: `tinygo build` errors with the version check on Go ≥ 1.26.

**Fix**: prepend the Go 1.23.12 SDK to `PATH` — every `tinygo build`
command in [../build/wasm-variants.md](../build/wasm-variants.md) does
this:

```bash
PATH="$HOME/sdk/go1.23.12/bin:$PATH" \
  tinygo build -target=wasip1 -gc=conservative -opt=2 -no-debug -o app.wasm .
```

If `~/sdk/go1.23.12/bin/go` does not exist, you need to install it —
[../setup/01-prerequisites.md](../setup/01-prerequisites.md).

## Wasm-tinygo /fanout returns HTTP 500 with `sync.WaitGroup.Wait` panic

**Symptoms** (visible in `kubectl logs`): `panic: runtime error: nil
pointer dereference` with the trace passing through
`(*sync.WaitGroup).Wait`.

**Root cause**: TinyGo's wasip1 runtime panics on `sync.WaitGroup.Wait`
when used to await goroutines that call `spinhttp.Send`. This is a
known TinyGo + Spin + wasip1 limitation, not a bug in our code.

**Fix in the code**: the 03 wasm-tinygo handler now dispatches the N
outbound GETs **sequentially**. The trade-off (no concurrent fan-out
on the TinyGo + WASI P1 cell) is itself a thesis-relevant observation
documented in
[../benchmarks/03-http-fanout.md](../benchmarks/03-http-fanout.md).

If you see this error after pulling the repo, your `app.wasm` image
predates the fix — rebuild and re-push it per
[../build/wasm-variants.md](../build/wasm-variants.md).

## Pod ready but health check fails from outside the cluster

**Symptoms**: `kubectl get pods` shows `Running`, but
`curl http://${THESIS_NODE_IP}:30081/health` hangs from your
workstation.

**Common cause**: Hetzner firewall not opened on NodePort range
30000–32767. Check via the Hetzner Cloud Console → Firewalls.

## Prometheus query inside `run_experiment.sh` fails

If only the Prometheus call fails (k6 still runs), the orchestrator
prints `WARN: Prometheus query failed (continuing)` and proceeds —
your chart PNGs will be missing the memory and CPU panels for that
variant. Common causes:

1. `kube-prometheus-stack` was not deployed
   ([../setup/02-infrastructure.md](../setup/02-infrastructure.md)
   step 4).
2. The cluster API is wedged — see the collapse-recovery flow above.
3. The NodePort 32090 was not opened on the Hetzner firewall.

To re-query later (after the cluster recovers), re-run the orchestrator
with `--scaling-experiment limited` only — re-running is idempotent.

## Charts look stale after editing `analyze.py`

The orchestrator only calls `analyze.py` at the end of a full run.
After tweaking the chart code, regenerate without re-running the
benchmark — see
[../operate/output-structure.md](../operate/output-structure.md) for
the per-experiment `python3 analyze.py --mode ...` commands.
