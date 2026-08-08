# Verification status

Reference package verification performed in the build environment:

```text
python3 -m unittest discover -s tests -v
42 tests passed

python3 -m compileall -q model scripts tests
passed

sh -n scripts/compile.sh
passed

python3 scripts/demo.py
complete selection cycle and token-conservation invariant passed
```

The tests cover the executable Python state model, Ethereum-compatible Keccak and Merkle tooling, source-manifest determinism, Solidity import resolution, delimiter balance, pinned compiler identity, and static absence of owner/withdraw/halt/upgrade escape hatches.

## Important limitation

The Solidity contracts were **not compiled inside this artifact-building environment** because the pinned compiler binary could not be downloaded there. `scripts/compile.sh` and GitHub Actions CI pin official `solc 0.8.36+commit.8a079791` and verify SHA-256 before compilation, but a successful CI compile is still required before treating the Solidity source as build-verified.

No security audit, fuzz campaign, symbolic execution, formal proof, testnet deployment, or mainnet deployment has been performed. Demo verifiers are explicitly insecure and must not be used with value.
