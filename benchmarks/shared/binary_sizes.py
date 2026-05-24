"""
Collect raw binary artifact sizes (one file per variant, MB) and write
results/<example>/binary_sizes.json.

Distinct from results/<example>/image_sizes.json:
  - binary_sizes.json:  the compiled artifact alone — the .wasm file for the
                        two Spin variants, the stripped scratch binary for the
                        two Docker variants.
  - image_sizes.json:   the full OCI image — Spin OCI artifact for the Spin
                        variants, scratch + ca-certificates + binary for the
                        Docker variants.

For our scratch-based Docker images OCI ≈ binary + ~100 KB (cert bundle +
image metadata). For Spin images OCI ≈ .wasm + a small Spin manifest layer.
binary_sizes isolates "the compiled code" from "the container packaging" so
the cross-variant comparison is apples-to-apples.

Usage:
  python3 -m shared.binary_sizes --example 01-prime-sieve
  python3 -m shared.binary_sizes --example 03-http-fanout
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ── Per-example configuration ─────────────────────────────────────────────────
# Keyed by `--example` value (matches the results subdir name).
#
# Each entry:
#   docker_images: variant → (image:tag, /path/to/binary-inside-scratch)
#   spin_wasm:     variant → relative path to the .wasm file under the repo root
#
# Variant ordering follows port-ascending convention (wasm-rust → wasm-tinygo →
# docker-rust → docker-golang).
EXAMPLES: dict[str, dict] = {
    "01-prime-sieve": {
        "docker_images": {
            "docker-rust":   ("docker.io/abdulaziz7225/prime-sieve-docker-rust:latest",   "/prime-sieve"),
            "docker-golang": ("docker.io/abdulaziz7225/prime-sieve-docker-golang:latest", "/prime-sieve"),
        },
        "spin_wasm": {
            "wasm-rust":   "wasm/rust/01-prime-sieve/target/wasm32-wasip1/release/prime_sieve_spin.wasm",
            "wasm-tinygo": "wasm/tinygo/01-prime-sieve/app.wasm",
        },
    },
    "02-memory-bandwidth": {
        "docker_images": {
            "docker-rust":   ("docker.io/abdulaziz7225/memory-bandwidth-docker-rust:latest",   "/memory-bandwidth"),
            "docker-golang": ("docker.io/abdulaziz7225/memory-bandwidth-docker-golang:latest", "/memory-bandwidth"),
        },
        "spin_wasm": {
            "wasm-rust":   "wasm/rust/02-memory-bandwidth/target/wasm32-wasip1/release/memory_bandwidth_spin.wasm",
            "wasm-tinygo": "wasm/tinygo/02-memory-bandwidth/app.wasm",
        },
    },
    "03-http-fanout": {
        "docker_images": {
            "docker-rust":   ("docker.io/abdulaziz7225/http-fanout-docker-rust:latest",   "/http-fanout"),
            "docker-golang": ("docker.io/abdulaziz7225/http-fanout-docker-golang:latest", "/http-fanout"),
        },
        "spin_wasm": {
            "wasm-rust":   "wasm/rust/03-http-fanout/target/wasm32-wasip1/release/http_fanout_spin.wasm",
            "wasm-tinygo": "wasm/tinygo/03-http-fanout/app.wasm",
        },
    },
    "04-json-roundtrip": {
        "docker_images": {
            "docker-rust":   ("docker.io/abdulaziz7225/json-roundtrip-docker-rust:latest",   "/json-roundtrip"),
            "docker-golang": ("docker.io/abdulaziz7225/json-roundtrip-docker-golang:latest", "/json-roundtrip"),
        },
        "spin_wasm": {
            "wasm-rust":   "wasm/rust/04-json-roundtrip/target/wasm32-wasip1/release/json_roundtrip_spin.wasm",
            "wasm-tinygo": "wasm/tinygo/04-json-roundtrip/app.wasm",
        },
    },
}


_BYTES_PER_MB = 1_048_576


def _bytes_to_mb(n: int) -> float:
    return round(n / _BYTES_PER_MB, 2)


def collect_docker_binary_size(image: str, binary_path: str) -> int | None:
    """
    Extract the binary from a Docker image via a throwaway container and
    return its size in bytes. Returns None if the image is not locally
    available or `docker cp` fails.
    """
    if subprocess.run(["docker", "image", "inspect", image],
                      capture_output=True).returncode != 0:
        return None

    tmp_container = f"_binsizes_{os.getpid()}_{abs(hash(image)) & 0xFFFF:x}"
    create = subprocess.run(
        ["docker", "create", "--name", tmp_container, image],
        capture_output=True, text=True,
    )
    if create.returncode != 0:
        return None

    try:
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / Path(binary_path).name
            cp = subprocess.run(
                ["docker", "cp", f"{tmp_container}:{binary_path}", str(dst)],
                capture_output=True, text=True,
            )
            if cp.returncode != 0 or not dst.exists():
                return None
            return dst.stat().st_size
    finally:
        subprocess.run(["docker", "rm", tmp_container], capture_output=True)


def collect_wasm_binary_size(repo_root: Path, rel_path: str) -> int | None:
    p = repo_root / rel_path
    return p.stat().st_size if p.is_file() else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--example", required=True, choices=list(EXAMPLES.keys()),
        help="Which experiment to collect binary sizes for.",
    )
    parser.add_argument(
        "--repo-root", default=None,
        help="Override the repo root (default: two levels up from this script).",
    )
    args = parser.parse_args()

    repo_root = (
        Path(args.repo_root).resolve()
        if args.repo_root
        else Path(__file__).resolve().parents[2]
    )

    cfg = EXAMPLES[args.example]
    sizes_mb: dict[str, float] = {}

    # Order matches the port-ascending convention.
    for variant, rel_path in cfg["spin_wasm"].items():
        n = collect_wasm_binary_size(repo_root, rel_path)
        if n is not None:
            sizes_mb[variant] = _bytes_to_mb(n)
        else:
            print(f"  WARN: {rel_path} not found – build first", file=sys.stderr)

    for variant, (image, binary_path) in cfg["docker_images"].items():
        n = collect_docker_binary_size(image, binary_path)
        if n is not None:
            sizes_mb[variant] = _bytes_to_mb(n)
        else:
            print(f"  WARN: could not extract {binary_path} from {image}", file=sys.stderr)

    out_path = repo_root / "results" / args.example / "binary_sizes.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sizes_mb, indent=2))
    print(f"  Saved {out_path}")
    for k, v in sizes_mb.items():
        print(f"    {k}: {v} MB")
    if len(sizes_mb) < 4:
        missing = [v for v in (
            list(cfg["spin_wasm"].keys()) + list(cfg["docker_images"].keys())
        ) if v not in sizes_mb]
        print(f"  NOTE: {len(sizes_mb)}/4 sizes collected. Missing: {missing}")


if __name__ == "__main__":
    main()
