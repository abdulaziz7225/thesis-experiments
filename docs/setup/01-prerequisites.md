# Local prerequisites

These are the tools you install on your **workstation** (not the cluster
node) before you can build images, drive `kubectl`, or run benchmarks.
Run each block once, in order. After this file is done, follow on to
[02-infrastructure.md](02-infrastructure.md) to bring the cluster up.

Pinned versions of every component are in
[../reference/toolchain-versions.md](../reference/toolchain-versions.md).

## Clone the two source repositories as siblings

The experiment artefact bundle lives in **two** GitHub repositories that
must be cloned **side by side** under the same parent directory. Every
command in the docs assumes this layout, because the orchestrator scripts
reference the infra repo via the relative path `../thesis-infra-setup/`.

```bash
mkdir -p ~/master-thesis && cd ~/master-thesis

git clone https://github.com/abdulaziz7225/thesis-experiments.git
git clone https://github.com/abdulaziz7225/thesis-infra-setup.git

# Expected layout after this step:
#   ~/master-thesis/
#   ├── thesis-experiments/      ← this repo (the benchmark workloads + docs)
#   └── thesis-infra-setup/      ← sibling repo (Terraform + cloud-init + Helm for the cluster)

cd thesis-experiments
```

If you already have one of the two and want to add the other, just
`git clone` the missing one into the same parent directory — the
relative paths in the commands depend only on the **sibling**
relationship.

## Python virtualenv (for the benchmark harness)

```bash
cd thesis-experiments
python3 -m venv .venv
source .venv/bin/activate
pip install -r benchmarks/requirements.txt
```

## Docker (for building Docker images)

```bash
docker info   # verify the daemon is running
```

If `docker info` fails, install Docker Desktop or set up rootless
docker first.

## Spin CLI (for building and pushing Spin / WASI P2 OCI images)

```bash
curl -fsSL https://developer.fermyon.com/downloads/install.sh | bash
spin --version   # expected: v3+
```

## cargo-component (for Rust WASI P2 components)

```bash
cargo install cargo-component
```

## TinyGo + Go 1.23.12 SDK — required for the wasm-tinygo variants

> **Important toolchain pin.** TinyGo 0.40.1 rejects Go ≥ 1.26 outright,
> and Go 1.24 / 1.25 trigger `crypto/sha256` panics inside the TinyGo
> wasip1 runtime. **Go 1.23.12 is the only known-good version.**

Install Go 1.23.12 side-by-side with whatever system Go you already have,
via the official `go install golang.org/dl/...` mechanism (does **not**
replace the system Go):

```bash
go install golang.org/dl/go1.23.12@latest
go1.23.12 download
# Lands in ~/sdk/go1.23.12/
```

The `tinygo build` commands documented in
[../build/wasm-variants.md](../build/wasm-variants.md) prepend
`~/sdk/go1.23.12/bin` to `PATH` so TinyGo invokes the correct Go.

You also need TinyGo itself installed (per the
[upstream instructions](https://tinygo.org/getting-started/install/)) —
version 0.40.1.

## kubectl pointing to the Hetzner cluster

Set this **after** the infra is up (see
[02-infrastructure.md](02-infrastructure.md)):

```bash
export KUBECONFIG=../thesis-infra-setup/hetzner-thesis.yaml
```

## k6 (for HTTP load tests)

```bash
# Debian / Ubuntu
sudo gpg -k && sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
    --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
    | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6

# macOS
brew install k6
```
