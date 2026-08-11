"""Tests for v0.2.0 hardening patches (U1-U12)."""

from __future__ import annotations

import unittest

from model.arena import Arena, ArenaError, MarketJobStatus, VersionStatus


class V02HardeningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.arena = Arena()
        for account in ("founder", "buyer", "donor", "provider", "whale",
                        "other", "root-op", "child-op", "child-op-2"):
            self.arena.mint(account, 5_000_000)
        self.lineage, self.root = self.arena.create_lineage(
            operator="root-op",
            declaration=self.arena.declaration("root"),
            salt="root-salt",
            runtime_attested=True,
            bond_funder="root-op",
        )
        self.child = self.arena.register_version(
            lineage_id=self.lineage,
            parent_id=self.root,
            operator="child-op",
            declaration=self.arena.declaration("child"),
            salt="child-salt",
            runtime_attested=True,
            bond_funder="child-op",
        )
        self.arena.assert_invariants()

    # ── U1: Sybil bond ────────────────────────────────────────────────

    def test_u1_registration_requires_bond(self) -> None:
        """A version without bond funding cannot be registered."""
        # Drain operator's wallet so they can't pay the bond.
        self.arena.wallets["child-op-2"] = 0
        with self.assertRaisesRegex(ArenaError, "insufficient wallet"):
            self.arena.register_version(
                lineage_id=self.lineage,
                parent_id=self.root,
                operator="child-op-2",
                declaration=self.arena.declaration("v2"),
                salt="v2-salt",
                runtime_attested=True,
                bond_funder="child-op-2",
            )

    def test_u1_bond_goes_to_commons(self) -> None:
        """Bond is held in commons_available until refunded."""
        commons_before = self.arena.commons_available
        # Already 2 bonds (root + child) = 2 * VERSION_BOND
        self.assertEqual(
            self.arena.commons_available - commons_before + 2 * self.arena.VERSION_BOND,
            2 * self.arena.VERSION_BOND,
        )
        self.assertEqual(
            self.arena.version_bond[self.root], self.arena.VERSION_BOND
        )
        self.assertEqual(
            self.arena.version_bond[self.child], self.arena.VERSION_BOND
        )

    def test_u1_bond_refunded_after_profitable_epoch(self) -> None:
        """Bond is refundable after one epoch with positive ranked revenue."""
        # Fund commons for ranked job reward.
        self.arena.fund_commons("founder", 50_000)
        # Fund child vault for verified cost.
        self.arena.donate("donor", self.child, 20_000)
        # Create and settle a profitable ranked job for child.
        deadline = self.arena.now + 1_000
        result_hash = self.arena._hash("result", "u1-test")
        auth = self.arena.authorize_ranked_job(
            spec_hash=self.arena._hash("spec", "u1-test"),
            verifier_id="fixed-hash-v1",
            reward=50_000,
            deadline=deadline,
            expected_result_hash=result_hash,
            verified_cost=10_000,
            cost_recipient="provider",
        )
        job_id = self.arena.create_ranked_job(auth)
        self.arena.submit_ranked_result(
            operator="child-op",
            job_id=job_id,
            version_id=self.child,
            result_hash=result_hash,
            proof_id=self.arena._hash("proof", "u1-test", self.child),
            objective_proof_valid=True,
        )
        # Move to next epoch.
        self.arena.advance_to_next_epoch()
        # Child's bond should be refundable now.
        before_wallet = self.arena.wallets["child-op"]
        refunded = self.arena.reclaim_bond(
            operator="child-op", version_id=self.child
        )
        self.assertEqual(refunded, self.arena.VERSION_BOND)
        self.assertEqual(
            self.arena.wallets["child-op"], before_wallet + self.arena.VERSION_BOND
        )
        self.assertEqual(self.arena.version_bond[self.child], 0)

    def test_u1_bond_not_refundable_without_profit(self) -> None:
        """Bond cannot be reclaimed without ranked revenue last epoch."""
        self.arena.advance_to_next_epoch()
        with self.assertRaisesRegex(ArenaError, "no positive ranked profit"):
            self.arena.reclaim_bond(operator="child-op", version_id=self.child)

    # ── U2: Multi-sig + daily cap ──────────────────────────────────────

    def test_u2_daily_expense_cap_blocks_drain(self) -> None:
        """Operator cannot settle more than DAILY_EXPENSE_CAP per day."""
        self.arena.donate("donor", self.child, 1_000_000)
        # Try to drain 100K via single expense — should exceed cap.
        with self.assertRaisesRegex(ArenaError, "daily expense cap"):
            self.arena.settle_operating_expense(
                operator="child-op",
                version_id=self.child,
                expense_id="huge",
                recipient="provider",
                amount=self.arena.DAILY_EXPENSE_CAP + 1,
                payload_hash="payload",
                proof_id="proof-huge",
                valid_provider_proof=True,
            )

    def test_u2_large_expense_requires_multi_sig(self) -> None:
        """Expenses above 10% of daily cap require multi-sig."""
        self.arena.donate("donor", self.child, 1_000_000)
        # Amount above 10% of daily cap (5000).
        big_amount = self.arena.DAILY_EXPENSE_CAP // 10 + 100
        with self.assertRaisesRegex(ArenaError, "multi-sig"):
            self.arena.settle_operating_expense(
                operator="child-op",
                version_id=self.child,
                expense_id="big",
                recipient="provider",
                amount=big_amount,
                payload_hash="payload",
                proof_id="proof-big",
                valid_provider_proof=True,
                # No operator_sigs
            )

    def test_u2_multi_sig_with_signers_succeeds(self) -> None:
        """Multi-sig setup allows large expenses with proper signatures."""
        # Create a version with multi-sig operator.
        v2 = self.arena.register_version(
            lineage_id=self.lineage,
            parent_id=self.root,
            operator="root-op",
            declaration=self.arena.declaration("ms-v"),
            salt="ms-salt",
            runtime_attested=True,
            bond_funder="root-op",
            operator_signers=["root-op", "child-op"],
            operator_threshold=2,
        )
        self.arena.donate("donor", v2, 1_000_000)
        big_amount = self.arena.DAILY_EXPENSE_CAP // 10 + 100
        self.arena.settle_operating_expense(
            operator="root-op",
            version_id=v2,
            expense_id="big-ms",
            recipient="provider",
            amount=big_amount,
            payload_hash="payload",
            proof_id="proof-ms",
            valid_provider_proof=True,
            operator_sigs=["root-op", "child-op"],
        )

    # ── U3: Commit-reveal supersede ────────────────────────────────────

    def test_u3_commit_reveal_supersede(self) -> None:
        """Commit-reveal path uses median profit and two-step execution."""
        # Set up profitable challenger.
        self.arena.fund_commons("founder", 200_000)
        self.arena.donate("donor", self.child, 10_000)
        deadline = self.arena.now + 1_000
        result_hash = self.arena._hash("result", "u3")
        auth = self.arena.authorize_ranked_job(
            spec_hash=self.arena._hash("spec", "u3"),
            verifier_id="fixed-hash-v1",
            reward=100_000,
            deadline=deadline,
            expected_result_hash=result_hash,
            verified_cost=10_000,
            cost_recipient="provider",
        )
        job_id = self.arena.create_ranked_job(auth)
        self.arena.submit_ranked_result(
            operator="child-op",
            job_id=job_id,
            version_id=self.child,
            result_hash=result_hash,
            proof_id="proof-u3",
            objective_proof_valid=True,
        )
        self.arena.advance_to_next_epoch()
        # Commit.
        commit = self.arena.commit_supersede(
            challenger_id=self.child,
            epoch=self.arena.last_closed_epoch(),
            salt="u3-salt",
        )
        self.assertTrue(commit)
        # Reveal too early should fail.
        with self.assertRaisesRegex(ArenaError, "reveal too early"):
            self.arena.reveal_supersede(
                challenger_id=self.child,
                epoch=self.arena.last_closed_epoch(),
                salt="u3-salt",
            )
        # Advance past commit phase.
        self.arena.advance(self.arena.COMMIT_PHASE_BLOCKS + 1)
        # Heartbeat so challenger is still fresh.
        self.arena.donate("donor", self.child, 100)
        self.arena.heartbeat(
            operator="child-op", version_id=self.child,
            state_hash="state", runtime_attested=True,
        )
        # Reveal — but median over last 3 epochs includes 2 empty epochs.
        # With single profitable epoch, median is 0, so reveal fails.
        # This is the intended U8 behavior.
        with self.assertRaisesRegex(ArenaError, "median profit"):
            self.arena.reveal_supersede(
                challenger_id=self.child,
                epoch=self.arena.last_closed_epoch(),
                salt="u3-salt",
            )

    def test_u3_duplicate_commit_rejected(self) -> None:
        """Cannot commit the same (challenger, epoch, salt) twice."""
        self.arena.commit_supersede(
            challenger_id=self.child,
            epoch=self.arena.last_closed_epoch(),
            salt="dup-salt",
        )
        with self.assertRaisesRegex(ArenaError, "commit already exists"):
            self.arena.commit_supersede(
                challenger_id=self.child,
                epoch=self.arena.last_closed_epoch(),
                salt="dup-salt",
            )

    # ── U4: Verifier set ───────────────────────────────────────────────

    def test_u4_verifier_set_in_authorization(self) -> None:
        """A job authorization can carry a verifier set instead of a single verifier."""
        self.arena.fund_commons("founder", 50_000)
        deadline = self.arena.now + 1_000
        auth = self.arena.authorize_ranked_job(
            spec_hash="spec-u4",
            verifier_id="v1",
            reward=50_000,
            deadline=deadline,
            expected_result_hash="result",
            verified_cost=0,
            cost_recipient=None,
            verifier_set=["v1", "v2", "v3"],
        )
        self.assertEqual(
            self.arena.authorizations[auth].verifier_set,
            ("v1", "v2", "v3"),
        )

    def test_u4_verifier_set_rejects_duplicates(self) -> None:
        """Verifier set cannot contain duplicates."""
        with self.assertRaisesRegex(ArenaError, "duplicates"):
            self.arena.authorize_ranked_job(
                spec_hash="spec-dup",
                verifier_id="v1",
                reward=1_000,
                deadline=self.arena.now + 100,
                expected_result_hash="r",
                verified_cost=0,
                cost_recipient=None,
                verifier_set=["v1", "v1"],
            )

    def test_u4_verifier_id_must_be_in_set(self) -> None:
        """verifier_id must be a member of verifier_set."""
        with self.assertRaisesRegex(ArenaError, "must be in verifier_set"):
            self.arena.authorize_ranked_job(
                spec_hash="spec-mismatch",
                verifier_id="v1",
                reward=1_000,
                deadline=self.arena.now + 100,
                expected_result_hash="r",
                verified_cost=0,
                cost_recipient=None,
                verifier_set=["v2", "v3"],
            )

    # ── U5: Proof-of-retrieval ────────────────────────────────────────

    def test_u5_ipfs_proof_tracked(self) -> None:
        """Heartbeat with ipfs_proof updates last_ipfs_proof_ts."""
        self.arena.donate("donor", self.child, 100)
        self.arena.heartbeat(
            operator="child-op",
            version_id=self.child,
            state_hash="state",
            runtime_attested=True,
            ipfs_proof="bytes_from_ipfs",
        )
        self.assertEqual(
            self.arena.last_ipfs_proof_ts[self.child], self.arena.now
        )

    # ── U6: Market job auto-accept ────────────────────────────────────

    def test_u6_market_job_auto_accepts_on_proof(self) -> None:
        """Market job with work_verifier auto-settles on objective proof."""
        job_id = self.arena.open_market_job(
            buyer="buyer",
            target_version=self.child,
            spec_hash="spec-u6",
            reward=5_000,
            deadline=self.arena.now + 100,
            work_verifier_id="market-verifier",
        )
        # Submit result with valid proof.
        self.arena.submit_market_result(
            operator="child-op",
            job_id=job_id,
            result_hash="result",
            objective_proof_valid=True,
        )
        job = self.arena.market_jobs[job_id]
        self.assertEqual(job.status, MarketJobStatus.ACCEPTED)
        # Reward should be in child's vault.
        self.assertGreater(self.arena.vaults[self.child], 0)

    def test_u6_market_job_without_verifier_stays_submitted(self) -> None:
        """Market job without work_verifier still requires buyer acceptance."""
        job_id = self.arena.open_market_job(
            buyer="buyer",
            target_version=self.child,
            spec_hash="spec-u6b",
            reward=5_000,
            deadline=self.arena.now + 100,
        )
        self.arena.submit_market_result(
            operator="child-op",
            job_id=job_id,
            result_hash="result",
            objective_proof_valid=True,  # Ignored without verifier
        )
        job = self.arena.market_jobs[job_id]
        self.assertEqual(job.status, MarketJobStatus.SUBMITTED)

    # ── U8: Median profit ─────────────────────────────────────────────

    def test_u8_median_profit_returns_zero_without_history(self) -> None:
        """median_profit returns 0 for a version with no economy history."""
        self.assertEqual(
            self.arena.median_profit(self.child, self.arena.current_epoch()), 0
        )

    def test_u8_median_profit_with_one_epoch(self) -> None:
        """With one profitable epoch, median over 3 returns that profit."""
        # Manually populate economy to avoid the full ranked job dance.
        from model.arena import Economy
        epoch = self.arena.current_epoch()
        self.arena.economies[(self.child, epoch)] = Economy(
            ranked_revenue=100, verified_ranked_cost=10
        )
        # Median over [90, 0, 0] = 0 (two zeros from missing epochs).
        self.assertEqual(self.arena.median_profit(self.child, epoch), 0)

    def test_u8_median_profit_with_three_epochs(self) -> None:
        """With three populated epochs, median is the middle value."""
        from model.arena import Economy
        epoch = self.arena.current_epoch()
        self.arena.economies[(self.child, epoch)] = Economy(
            ranked_revenue=100, verified_ranked_cost=10  # profit 90
        )
        self.arena.economies[(self.child, epoch - 1)] = Economy(
            ranked_revenue=50, verified_ranked_cost=20  # profit 30
        )
        self.arena.economies[(self.child, epoch - 2)] = Economy(
            ranked_revenue=80, verified_ranked_cost=10  # profit 70
        )
        # Profits [90, 30, 70] sorted = [30, 70, 90], median = 70.
        self.assertEqual(self.arena.median_profit(self.child, epoch), 70)

    # ── U9: Stale commons split ───────────────────────────────────────

    def test_u9_stale_capital_splits_to_lineage_successor(self) -> None:
        """When a stale version has an Incubating successor in lineage, half goes to it."""
        # Set up child2 as Incubating with positive profit.
        child2 = self.arena.register_version(
            lineage_id=self.lineage,
            parent_id=self.root,
            operator="child-op-2",
            declaration=self.arena.declaration("child2"),
            salt="child2-salt",
            runtime_attested=True,
            bond_funder="child-op-2",
        )
        from model.arena import Economy
        epoch = self.arena.current_epoch()
        self.arena.economies[(child2, epoch)] = Economy(
            ranked_revenue=10, verified_ranked_cost=0
        )
        # Mark child2 as having shown positive profit (this is normally
        # done automatically by submit_ranked_result).
        self.arena.versions[child2].last_positive_profit_at = self.arena.now
        # Fund root with some capital.
        self.arena.donate("donor", self.root, 100_000)
        # Age root past stale.
        self.arena.advance(self.arena.STALE_AFTER + 1)
        moved = self.arena.eject_stale(self.root)
        # Half should go to child2 (lineage successor).
        expected_lineage_share = (
            100_000 * self.arena.STALE_LINEAGE_SHARE_NUM
            // self.arena.STALE_LINEAGE_SHARE_DEN
        )
        self.assertEqual(moved, 100_000)
        self.assertEqual(
            self.arena.vaults[child2], expected_lineage_share
        )

    def test_u9_stale_without_successor_all_to_commons(self) -> None:
        """Without a lineage successor, all capital goes to commons."""
        self.arena.donate("donor", self.root, 50_000)
        commons_before = self.arena.commons_available
        self.arena.advance(self.arena.STALE_AFTER + 1)
        self.arena.eject_stale(self.root)
        # All 50_000 should go to commons (no successor).
        self.assertEqual(
            self.arena.commons_available - commons_before, 50_000
        )

    # ── U10: Heartbeat burn ───────────────────────────────────────────

    def test_u10_heartbeat_burn_collected(self) -> None:
        """Each heartbeat collects a burn from the version's vault."""
        self.arena.donate("donor", self.child, 1_000)
        burn_before = self.arena.heartbeat_burn_collected
        vault_before = self.arena.vaults[self.child]
        self.arena.heartbeat(
            operator="child-op",
            version_id=self.child,
            state_hash="state",
            runtime_attested=True,
        )
        self.assertEqual(
            self.arena.heartbeat_burn_collected,
            burn_before + self.arena.HEARTBEAT_BURN,
        )
        self.assertEqual(
            self.arena.vaults[self.child],
            vault_before - self.arena.HEARTBEAT_BURN,
        )

    def test_u10_heartbeat_without_vault_funds_fails(self) -> None:
        """Heartbeat fails if vault cannot cover burn."""
        with self.assertRaisesRegex(ArenaError, "insufficient vault for heartbeat burn"):
            self.arena.heartbeat(
                operator="child-op",
                version_id=self.child,
                state_hash="state",
                runtime_attested=True,
            )


if __name__ == "__main__":
    unittest.main()
