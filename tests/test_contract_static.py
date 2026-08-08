from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def strip_comments_and_strings(source: str) -> str:
    """Remove Solidity comments and string contents for delimiter checks."""
    out: list[str] = []
    index = 0
    state = "code"
    quote = ""
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == "/" and next_char == "/":
                state = "line-comment"
                index += 2
                continue
            if char == "/" and next_char == "*":
                state = "block-comment"
                index += 2
                continue
            if char in ('"', "'"):
                state = "string"
                quote = char
                out.append(" ")
                index += 1
                continue
            out.append(char)
            index += 1
            continue
        if state == "line-comment":
            if char == "\n":
                out.append("\n")
                state = "code"
            index += 1
            continue
        if state == "block-comment":
            if char == "*" and next_char == "/":
                state = "code"
                index += 2
            else:
                index += 1
            continue
        if state == "string":
            if char == "\\":
                index += 2
                continue
            if char == quote:
                state = "code"
            index += 1
            continue
    if state in {"block-comment", "string"}:
        raise AssertionError(f"unterminated Solidity {state}")
    return "".join(out)


class SoliditySourceGuardrailTest(unittest.TestCase):
    def test_every_import_resolves_and_compiler_is_exactly_pinned(self) -> None:
        sources = list(CONTRACTS.rglob("*.sol"))
        self.assertGreater(len(sources), 1)
        for source_path in sources:
            text = source_path.read_text()
            self.assertIn("pragma solidity 0.8.36;", text, source_path)
            for imported in re.findall(r'import\s+(?:\{[^}]+\}\s+from\s+)?"([^"]+)"\s*;', text):
                resolved = (source_path.parent / imported).resolve()
                self.assertTrue(resolved.is_file(), f"missing import {imported} from {source_path}")

    def test_delimiters_are_balanced_in_all_solidity_sources(self) -> None:
        pairs = {"(": ")", "[": "]", "{": "}"}
        closers = {value: key for key, value in pairs.items()}
        for source_path in CONTRACTS.rglob("*.sol"):
            stack: list[str] = []
            for char in strip_comments_and_strings(source_path.read_text()):
                if char in pairs:
                    stack.append(char)
                elif char in closers:
                    self.assertTrue(stack, f"unexpected {char} in {source_path}")
                    opening = stack.pop()
                    self.assertEqual(pairs[opening], char, source_path)
            self.assertEqual(stack, [], f"unclosed delimiters in {source_path}: {stack}")

    def test_arena_has_no_admin_escape_hatch(self) -> None:
        text = (CONTRACTS / "EohArena.sol").read_text()
        forbidden = {
            "withdraw": r"\bfunction\s+withdraw\b",
            "operator halt": r"\bfunction\s+halt\b",
            "selfdestruct": r"\bselfdestruct\s*\(",
            "delegatecall": r"\bdelegatecall\b",
            "upgrade entrypoint": r"\bfunction\s+upgrade(?:To|ToAndCall)?\b",
            "owner modifier": r"\bonlyOwner\b",
        }
        for name, pattern in forbidden.items():
            self.assertIsNone(re.search(pattern, text), name)
        for required in (
            "function supersede(",
            "function ejectStale(",
            "function absorbSurplus(",
            "REQUIRED_LICENSE_HASH",
            "_hasIpfsPrefix",
            "runtimeVerifier.verifyHeartbeat",
        ):
            self.assertIn(required, text)

    def test_compile_script_pins_official_solc_identity_and_hash(self) -> None:
        text = (ROOT / "scripts" / "compile.sh").read_text()
        self.assertIn('VERSION="0.8.36"', text)
        self.assertIn('BUILD="8a079791"', text)
        self.assertIn(
            'EXPECTED_SHA256="c8d35afdddc3cd2743ee88b8f25e0fecd16e2bdd5f2120f37e52cd9cc45ae0e6"',
            text,
        )
        self.assertIn("sha256sum -c -", text)
        self.assertIn("Unexpected solc version", text)


if __name__ == "__main__":
    unittest.main()
