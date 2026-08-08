#!/usr/bin/env python3
"""Create a deterministic source manifest suitable for IPFS publication."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

EXCLUDED = {".git", ".cache", "__pycache__", "artifacts", "build", "out"}


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("source-manifest.json"))
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--provenance-digest", required=True)
    parser.add_argument("--source-uri", default="")
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output.resolve()
    digest_pattern = re.compile(r"^sha256:[0-9a-f]{64}$")
    for label, value in (
        ("image digest", args.image_digest),
        ("provenance digest", args.provenance_digest),
    ):
        if not digest_pattern.fullmatch(value):
            raise SystemExit(f"{label} must be sha256:<64 lowercase hex characters>")
    if args.source_uri and not args.source_uri.startswith("ipfs://"):
        raise SystemExit("source URI must be empty or start with ipfs://")

    files = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.resolve() == output:
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        files.append(
            {
                "path": relative.as_posix(),
                "size": path.stat().st_size,
                "sha256": file_digest(path),
            }
        )

    canonical_files = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    source_digest = hashlib.sha256(canonical_files).hexdigest()
    manifest = {
        "schema": "eoh.source-manifest.v1",
        "license": "AGPL-3.0-or-later",
        "source_digest": "0x" + source_digest,
        "image_digest": args.image_digest,
        "provenance_digest": args.provenance_digest,
        "source_uri": args.source_uri,
        "files": files,
    }
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(manifest["source_digest"])


if __name__ == "__main__":
    main()
