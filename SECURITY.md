# Security policy

This repository is a reference implementation and has not been audited.
Do not deploy it with real value.

## v0.2.0 status

v0.2.0 adds 10 hardening patches (U1-U12, see `docs/CRITIQUE.md` and
`CHANGELOG.md`). These patches close known v0.1.0 attack vectors but
have not themselves been audited. The Python model is the source of
truth; the Solidity contract mirrors it but is not yet formally
verified.

## Reporting vulnerabilities

Report vulnerabilities privately to the repository maintainer. Include:

- affected commit;
- minimal reproduction;
- violated invariant;
- impact on token conservation, selection, replay protection or attestation;
- suggested remediation if known.

## Production readiness checklist

Production readiness requires at minimum:

1. successful pinned-solc compilation (v0.2.0 adds new storage fields
   and functions — must recompile and verify bytecode hashes);
2. unit and integration tests on an EVM (v0.2.0 patches need their
   own EVM tests, not just the Python model);
3. invariant fuzzing (especially around U3 commit-reveal timing,
   U4 verifier-set entropy, U8 median edge cases);
4. static analysis (Slither, Mythril on the v0.2.0 contract);
5. independent smart-contract audit;
6. verifier-specific audit (Demo verifiers remain insecure — must be
   replaced with production TEE/zkVM verifiers);
7. testnet adversarial competition;
8. explicit settlement-token and chain risk review;
9. **NEW**: commit-reveal builder-anchor attack analysis (can a
   block builder include both commit and reveal in the same block,
   bypassing the COMMIT_PHASE_BLOCKS window?);
10. **NEW**: verifier-set entropy analysis (does `keccak256(blockhash,
    jobId)` provide sufficient randomness? Is `blockhash` manipulable
    by miners in the same block?).

## Known open issues in v0.2.0

- `claimVacancy` does NOT yet use commit-reveal (only `supersede` does).
  Production hardening should extend U3 to `claimVacancy`.
- U4 random verifier selection is not implemented in the Python model
  (the model uses `verifier_id` from the authorization). Production
  must implement on-chain entropy.
- U5 proof-of-retrieval is a flag, not a cryptographic proof. Production
  needs an actual IPFS retrieval proof (e.g., byte-range Merkle proof
  from a content-addressed chunk).
- U11 (production verifier as separate repo with formal verification)
  is a documentation item, not a code change.
- K18 (operator = address(this) edge case) is acknowledged but not
  fixed.
