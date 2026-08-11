# Changelog

## 0.2.0 — 2026-08-08

Hardening patches addressing the v0.1.0 threat model gaps. Mirrors
`docs/CRITIQUE.md` (U1-U12).

### Security patches

- **U1 Sybil bond** — `registerVersion` now requires a refundable bond
  (`VERSION_BOND = 1000` settlement units). Bond is held in
  `commonsAvailable` and returned after one epoch with positive ranked
  revenue via `reclaimBond`. Versions that go stale without earning
  forfeit the bond. Closes the v0.1.0 Sybil-registration attack (K3/A1).

- **U2 Multi-sig operator + daily expense cap** — `settleOperatingExpense`
  enforces `DAILY_EXPENSE_CAP = 50_000` per version per day. Expenses
  above 10% of the cap additionally require multi-sig signatures
  (`operator_threshold` of `operator_signers`). Closes the
  operator-compromise vault-drain attack (K4/A8).

- **U3 Commit-reveal supersede** — `commitSupersede` + `revealSupersede`
  replace the single-transaction `supersede` for the production path.
  Identity of the challenger is hidden during the commit window
  (`COMMIT_PHASE_BLOCKS = 4`), preventing block builders from
  prioritizing rival challengers. Closes the epoch-boundary MEV
  attack (K7/A3/A10).

- **U4 Verifier set** — `JobAuthorization` now carries a `verifier_set`
  tuple. Single-verifier jobs wrap into a 1-element set for backward
  compatibility. Production deployments select a random verifier per
  settlement via `keccak256(blockhash, jobId)` indexing. Closes the
  single-verifier collusion attack (K5/A2).

- **U5 Proof-of-retrieval** — `heartbeat` accepts an optional `ipfs_proof`
  field that updates `last_ipfs_proof_ts[versionId]`. Versions that
  cannot produce a fresh proof are flagged as suspects by indexers
  (off-chain). Closes the dead-CID version attack (K14/A9).

- **U6 Market job auto-accept** — `openMarketJob` accepts an optional
  `work_verifier_id`. If set and the submitted result carries a valid
  proof, the market job auto-settles on submit, bypassing buyer
  acceptance. Closes the buyer-griefing attack (K8/A4).

- **U7 `uint256` in `Economy`** — `rankedRevenue` and `verifiedRankedCost`
  bumped from `uint128` to `uint256` in the Solidity contract. Removes
  the (theoretical but real) truncation risk (K1).

- **U8 Median profit** — `median_profit(version_id, end_epoch)` returns
  the median over `PROFIT_WINDOW_EPOCHS = 3` epochs. The commit-reveal
  production supersede path uses this metric instead of single-epoch
  profit. Closes the single-epoch outlier attack (K15).

- **U9 Stale commons split** — `ejectStale` now splits the stale
  version's capital half to `commons` and half to an Incubating lineage
  successor with positive profit history. Without a successor, all
  capital goes to commons (v0.1.0 behavior). Preserves lineage
  economics against DoS attackers.

- **U10 Heartbeat micro-burn** — Each `heartbeat` debits
  `HEARTBEAT_BURN = 1` settlement unit from the version's vault and
  credits `commonsAvailable`. Heartbeat spam now costs proportional
  capital. Closes the heartbeat spam attack (A6).

### Documentation patches

- **U12 Settlement token allowlist** — `allowedSettlementTokens`
  mapping added. Production deployments must populate this mapping in
  the constructor (or via a separate initialization transaction) before
  any donation. Tokens not in the allowlist are rejected at the
  `settleOperatingExpense` boundary. Closes the fee-on-transfer drift
  attack (K17).

### Backward compatibility

The legacy `supersede()` entrypoint is preserved and uses single-epoch
profit (no commit-reveal, no median). It is intended for tests and
legacy integrations only.

### Test coverage

- 42 v0.1.0 tests pass unchanged (after `setUp` updates for bond funding).
- 22 new v0.2.0 tests in `tests/test_v02_hardening.py` cover each U1-U10 patch.
- Total: 64 tests, all green.

### Known limitations

- Solidity contract is **reference**, not audited. v0.2.0 patches mirror
  the Python model; production deployment requires formal verification
  and a security audit.
- U3 `claimVacancy` does NOT yet use commit-reveal in the Python model
  (only `supersede` does). Production hardening should extend this.
- U4 random verifier selection is not implemented in the Python model
  (the model uses `verifier_id` from the authorization). Production
  deployment must implement on-chain entropy from `blockhash`.
- Demo verifiers (`DemoExpenseVerifier`, `DemoRuntimeVerifier`,
  `FixedCostHashVerifier`) remain unchanged and are explicitly insecure.

## 0.1.0 — 2026-08-08

- Non-upgradeable `EohArena` reference contract.
- Permissionless open-source lineages and forks.
- Donation/market/ranked revenue separation.
- Immutable Merkle ranked-job schedule.
- Atomic result, verified-cost and reward settlement.
- Strict epoch-based supersession with capital inheritance.
- Thirty-day stale ejection into commons.
- Registration and heartbeat runtime-verifier interfaces.
- Deterministic Python state model and 42 unit tests.
- Source-manifest and Merkle-schedule tooling.
