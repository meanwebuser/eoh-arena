from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.keccak256 import keccak256
from scripts.make_job_tree import build_tree, job_leaf, pair_hash, proof_for


class ToolingTest(unittest.TestCase):
    def test_ethereum_keccak_vectors(self) -> None:
        self.assertEqual(
            keccak256(b"").hex(),
            "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470",
        )
        self.assertEqual(
            keccak256(b"abc").hex(),
            "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45",
        )

    def test_merkle_proofs_reconstruct_root(self) -> None:
        jobs = [
            {
                "spec_hash": "0x" + f"{index + 1:064x}",
                "verifier": "0x" + f"{index + 100:040x}",
                "reward": 1_000_000 + index,
                "deadline": 1_900_000_000 + index,
            }
            for index in range(5)
        ]
        leaves = [job_leaf(job) for job in jobs]
        layers = build_tree(leaves)
        root = layers[-1][0]
        for index, leaf in enumerate(leaves):
            computed = leaf
            for sibling in proof_for(layers, index):
                computed = pair_hash(computed, sibling)
            self.assertEqual(computed, root)

    def test_manifest_is_deterministic(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "build_source_manifest.py"
        with tempfile.TemporaryDirectory() as temp:
            out1 = Path(temp) / "one.json"
            out2 = Path(temp) / "two.json"
            common = [
                "python",
                str(script),
                str(root),
                "--image-digest",
                "sha256:" + "11" * 32,
                "--provenance-digest",
                "sha256:" + "22" * 32,
            ]
            subprocess.run(common + ["-o", str(out1)], check=True, capture_output=True, text=True)
            subprocess.run(common + ["-o", str(out2)], check=True, capture_output=True, text=True)
            first = json.loads(out1.read_text())
            second = json.loads(out2.read_text())
            self.assertEqual(first["source_digest"], second["source_digest"])
            self.assertEqual(first["files"], second["files"])

    def test_manifest_excludes_its_own_output_and_is_repeatable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "build_source_manifest.py"
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            (source / "agent.py").write_text("print('agent')\n")
            output = source / "source-manifest.json"
            command = [
                "python",
                str(script),
                str(source),
                "--image-digest",
                "sha256:" + "33" * 32,
                "--provenance-digest",
                "sha256:" + "44" * 32,
                "--source-uri",
                "ipfs://bafy-example",
                "-o",
                str(output),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            first = output.read_text()
            subprocess.run(command, check=True, capture_output=True, text=True)
            second = output.read_text()
            self.assertEqual(first, second)
            manifest = json.loads(second)
            self.assertEqual([item["path"] for item in manifest["files"]], ["agent.py"])

    def test_manifest_rejects_placeholder_digests(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "build_source_manifest.py"
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [
                    "python",
                    str(script),
                    temp,
                    "--image-digest",
                    "sha256:REPLACE_ME",
                    "--provenance-digest",
                    "sha256:" + "55" * 32,
                    "-o",
                    str(Path(temp) / "manifest.json"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("64 lowercase hex", result.stderr)


if __name__ == "__main__":
    unittest.main()
