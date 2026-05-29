# Local prerequisites

## Clone the two source repositories as siblings

The experiment artefact bundle lives in **two** GitHub repositories that
must be cloned **side by side** under the same parent directory. Every
command in the docs assumes this layout, because the orchestrator scripts
reference the infra repo via the relative path `../thesis-infra-setup/`.

```bash
mkdir -p ~/master-thesis && cd ~/master-thesis

git clone https://github.com/abdulaziz7225/thesis-experiments.git
git clone https://github.com/abdulaziz7225/thesis-infra-setup.git

cd thesis-experiments
```

## Python virtualenv (for the benchmark harness)

```bash
cd thesis-experiments
python3 -m venv .venv
source .venv/bin/activate
pip install -r benchmarks/requirements.txt
```

## Docker

```bash
docker info
```

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

Install Go 1.23.12 side-by-side with whatever system Go you already have,
via the official `go install golang.org/dl/...` mechanism (does **not**
replace the system Go):

```bash
go install golang.org/dl/go1.23.12@latest
go1.23.12 download
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
