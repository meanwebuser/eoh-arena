#!/usr/bin/env python3
"""Build the immutable ranked-job Merkle schedule used by Solidity.

Input JSON:
{
  "jobs": [
    {"spec_hash":"0x...", "verifier":"0x...", "reward":1000000,
     "deadline":1900000000}
  ]
}

Output contains each Solidity-compatible leaf, the sorted-pair Merkle root, and
ABI-encodable bytes32[] proofs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keccak256 import keccak256  # noqa: E402


def _bytes32(value: str) -> bytes:
    raw = bytes.fromhex(value.removeprefix("0x"))
    if len(raw) != 32:
        raise ValueError(f"expected bytes32, got {len(raw)} bytes")
    return raw


def _address_word(value: str) -> bytes:
    raw = bytes.fromhex(value.removeprefix("0x"))
    if len(raw) != 20:
        raise ValueError(f"expected address, got {len(raw)} bytes")
    return b"\x00" * 12 + raw


def _uint_word(value: int, bits: int) -> bytes:
    if value < 0 or value >= 1 << bits:
        raise ValueError(f"uint{bits} overflow")
    return value.to_bytes(32, "big")


def job_leaf(job: dict[str, object]) -> bytes:
    domain = keccak256(b"EOH_JOB_AUTH_V1")
    encoded = b"".join(
        (
            domain,
            _bytes32(str(job["spec_hash"])),
            _address_word(str(job["verifier"])),
            _uint_word(int(job["reward"]), 128),
            _uint_word(int(job["deadline"]), 64),
        )
    )
    return keccak256(encoded)


def pair_hash(left: bytes, right: bytes) -> bytes:
    return keccak256(left + right) if left < right else keccak256(right + left)


def build_tree(leaves: list[bytes]) -> list[list[bytes]]:
    if not leaves:
        raise ValueError("at least one job is required")
    layers = [leaves]
    while len(layers[-1]) > 1:
        current = layers[-1]
        nxt: list[bytes] = []
        for index in range(0, len(current), 2):
            left = current[index]
            right = current[index + 1] if index + 1 < len(current) else left
            nxt.append(pair_hash(left, right))
        layers.append(nxt)
    return layers


def proof_for(layers: list[list[bytes]], leaf_index: int) -> list[bytes]:
    proof: list[bytes] = []
    index = leaf_index
    for layer in layers[:-1]:
        sibling_index = index ^ 1
        sibling = layer[sibling_index] if sibling_index < len(layer) else layer[index]
        proof.append(sibling)
        index //= 2
    return proof


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("job-tree.json"))
    args = parser.parse_args()

    payload = json.loads(args.input.read_text())
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise SystemExit("input must contain a jobs array")
    leaves = [job_leaf(job) for job in jobs]
    layers = build_tree(leaves)
    output = {
        "schema": "eoh.job-tree.v1",
        "root": "0x" + layers[-1][0].hex(),
        "jobs": [
            {
                **job,
                "leaf": "0x" + leaves[index].hex(),
                "proof": ["0x" + item.hex() for item in proof_for(layers, index)],
            }
            for index, job in enumerate(jobs)
        ],
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(output["root"])


if __name__ == "__main__":
    main()
