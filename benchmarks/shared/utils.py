"""
Shared utilities for thesis benchmarking scripts.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

# ── Variant registry ─────────────────────────────────────────────────────────
# Maps short variant name → NodePort on the Hetzner server.
# Update NODE_IP via environment variable THESIS_NODE_IP.
VARIANTS: dict[str, int] = {
    "wasm-rust":    30081,
    "wasm-tinygo":  30082,
    "docker-rust":  30083,
    "docker-golang": 30084,
}

VARIANT_LABELS: dict[str, str] = {
    "wasm-rust":     "Rust + WASM",
    "wasm-tinygo":   "TinyGo + WASM",
    "docker-rust":   "Rust + Docker",
    "docker-golang": "Go + Docker",
}

VARIANT_COLORS: dict[str, str] = {
    "wasm-rust":     "#e07b39",   # orange  (WASM family)
    "wasm-tinygo":   "#f5c242",   # yellow
    "docker-rust":   "#3b82f6",   # blue    (Docker family)
    "docker-golang": "#22c55e",   # green
}


def node_ip() -> str:
    ip = os.environ.get("THESIS_NODE_IP", "")
    if not ip:
        raise EnvironmentError(
            "Set THESIS_NODE_IP to your Hetzner server's public IP.\n"
            "  export THESIS_NODE_IP=$(cd ../thesis-infra-setup && terraform output -raw instance_public_ip)"
        )
    return ip


def base_url(variant: str) -> str:
    """Return the HTTP base URL for a given variant."""
    port = VARIANTS[variant]
    return f"http://{node_ip()}:{port}"


# ── kubectl helpers ───────────────────────────────────────────────────────────
def kubeconfig_path() -> str:
    kc = os.environ.get(
        "KUBECONFIG",
        str(Path(__file__).parents[3] / "thesis-infra-setup" / "hetzner-thesis.yaml"),
    )
    return kc


def kubectl(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    cmd = ["kubectl", "--kubeconfig", kubeconfig_path(), *args]
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=True,
    )


def scale_deployment(name: str, namespace: str, replicas: int) -> None:
    kubectl("scale", "deployment", name, f"--replicas={replicas}", "-n", namespace)


def wait_for_ready(name: str, namespace: str, timeout: int = 120) -> None:
    kubectl(
        "rollout", "status",
        f"deployment/{name}",
        "-n", namespace,
        f"--timeout={timeout}s",
        capture=False,
    )


# ── Results helpers ───────────────────────────────────────────────────────────
RESULTS_DIR = Path(__file__).parents[2] / "results" / "01-prime-sieve"


def results_path(filename: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR / filename


def save_json(data: dict | list, filename: str) -> Path:
    path = results_path(filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved → {path}")
    return path


def load_json(filename: str) -> dict | list:
    with open(results_path(filename)) as f:
        return json.load(f)


# ── Health-check poll ─────────────────────────────────────────────────────────
def wait_for_http(url: str, path: str = "/health", timeout: float = 120.0) -> float:
    """
    Poll GET <url><path> until HTTP 200. Returns the elapsed time in seconds.
    Raises TimeoutError if the service does not respond within *timeout* seconds.
    """
    import requests  # local import so the module is usable without requests too

    deadline = time.monotonic() + timeout
    start = time.monotonic()

    while time.monotonic() < deadline:
        try:
            r = requests.get(f"{url}{path}", timeout=1.0)
            if r.status_code == 200:
                return time.monotonic() - start
        except Exception:
            pass
        time.sleep(0.05)

    raise TimeoutError(f"{url}{path} did not respond within {timeout}s")


# ── Prometheus helpers ────────────────────────────────────────────────────────
def prometheus_url() -> str:
    """Return the Prometheus base URL using THESIS_NODE_IP."""
    return f"http://{node_ip()}:32090"


def prometheus_query(query: str) -> list[dict[str, Any]]:
    """
    Run an instant Prometheus query and return the result list.
    Each element is {"metric": {...labels...}, "value": [timestamp, "value_str"]}.
    """
    import requests

    resp = requests.get(
        f"{prometheus_url()}/api/v1/query",
        params={"query": query},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data["status"] != "success":
        raise RuntimeError(f"Prometheus query failed: {data}")
    return data["data"]["result"]


def prometheus_query_range(
    query: str,
    start: float,
    end: float,
    step: str = "5s",
) -> list[dict[str, Any]]:
    """
    Run a range Prometheus query over [start, end] (Unix timestamps).
    Returns a list of series, each with "metric" labels and "values" [[ts, val], ...].
    """
    import requests

    resp = requests.get(
        f"{prometheus_url()}/api/v1/query_range",
        params={"query": query, "start": start, "end": end, "step": step},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data["status"] != "success":
        raise RuntimeError(f"Prometheus range query failed: {data}")
    return data["data"]["result"]
