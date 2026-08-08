# Security policy

This repository is a reference implementation and has not been audited.
Do not deploy it with real value.

Report vulnerabilities privately to the repository maintainer. Include:

- affected commit;
- minimal reproduction;
- violated invariant;
- impact on token conservation, selection, replay protection or attestation;
- suggested remediation if known.

Production readiness requires at minimum:

1. successful pinned-solc compilation;
2. unit and integration tests on an EVM;
3. invariant fuzzing;
4. static analysis;
5. independent smart-contract audit;
6. verifier-specific audit;
7. testnet adversarial competition;
8. explicit settlement-token and chain risk review.
