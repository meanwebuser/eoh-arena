from __future__ import annotations

import unittest

from model.arena import Arena, ArenaError, MarketJobStatus, RankedJobStatus, VersionStatus


class ArenaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.arena = Arena()
        # v0.2.0: include operator accounts so they can pay the Sybil bond.
        for account in ("founder", "buyer", "donor", "provider", "whale",
                        "other", "root-op", "child-op"):
            self.arena.mint(account, 2_000_000)
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

    def _ranked_job(
        self,
        *,
        name: str,
        reward: int,
        cost: int,
        version_id: str,
        operator: str,
    ) -> tuple[str, int]:
        self.arena.fund_commons("founder", reward)
        if cost:
            self.arena.donate("donor", version_id, cost)
        deadline = self.arena.now + 1_000
        result_hash = self.arena._hash("result", name)
        auth = self.arena.authorize_ranked_job(
            spec_hash=self.arena._hash("spec", name),
            verifier_id="fixed-hash-v1",
            reward=reward,
            deadline=deadline,
            expected_result_hash=result_hash,
            verified_cost=cost,
            cost_recipient="provider" if cost else None,
        )
        job_id = self.arena.create_ranked_job(auth)
        epoch = self.arena.current_epoch()
        self.arena.submit_ranked_result(
            operator=operator,
            job_id=job_id,
            version_id=version_id,
            result_hash=result_hash,
            proof_id=self.arena._hash("proof", name, version_id),
            objective_proof_valid=True,
        )
        return job_id, epoch

    def test_donation_does_not_change_rank(self) -> None:
        epoch = self.arena.current_epoch()
        self.arena.donate("whale", self.child, 1_000_000)
        self.assertEqual(self.arena.profit(self.child, epoch), 0)
        self.assertEqual(self.arena.capital_in[self.child], 1_000_000)
        self.arena.assert_invariants()

    def test_subjective_self_payment_does_not_change_rank(self) -> None:
        epoch = self.arena.current_epoch()
        job = self.arena.open_market_job(
            buyer="buyer",
            target_version=self.child,
            spec_hash="subjective-spec",
            reward=50_000,
            deadline=self.arena.now + 100,
        )
        self.arena.submit_market_result(operator="child-op", job_id=job, result_hash="anything")
        beneficiary = self.arena.accept_market_result(buyer="buyer", job_id=job)
        self.assertEqual(beneficiary, self.child)
        self.assertEqual(self.arena.market_revenue[self.child], 50_000)
        self.assertEqual(self.arena.profit(self.child, epoch), 0)
        self.arena.assert_invariants()

    def test_ranked_profit_is_reward_minus_atomic_verified_cost(self) -> None:
        job, epoch = self._ranked_job(
            name="net-profit", reward=100_000, cost=25_000, version_id=self.child, operator="child-op"
        )
        self.assertEqual(self.arena.ranked_jobs[job].status, RankedJobStatus.SETTLED)
        self.assertEqual(self.arena.profit(self.child, epoch), 75_000)
        self.assertEqual(self.arena.wallets["provider"], 2_025_000)
        self.assertEqual(self.arena.vaults[self.child], 100_000)
        self.arena.assert_invariants()

    def test_wrong_objective_result_is_rejected(self) -> None:
        self.arena.fund_commons("founder", 10_000)
        auth = self.arena.authorize_ranked_job(
            spec_hash="spec",
            verifier_id="v",
            reward=10_000,
            deadline=self.arena.now + 100,
            expected_result_hash="correct",
            verified_cost=0,
            cost_recipient=None,
        )
        job = self.arena.create_ranked_job(auth)
        with self.assertRaisesRegex(ArenaError, "wrong result"):
            self.arena.submit_ranked_result(
                operator="child-op",
                job_id=job,
                version_id=self.child,
                result_hash="wrong",
                proof_id="proof",
                objective_proof_valid=True,
            )
        self.assertEqual(self.arena.ranked_jobs[job].status, RankedJobStatus.OPEN)
        self.arena.assert_invariants()

    def test_invalid_objective_proof_is_rejected(self) -> None:
        self.arena.fund_commons("founder", 10_000)
        auth = self.arena.authorize_ranked_job(
            spec_hash="spec",
            verifier_id="v",
            reward=10_000,
            deadline=self.arena.now + 100,
            expected_result_hash="correct",
            verified_cost=0,
            cost_recipient=None,
        )
        job = self.arena.create_ranked_job(auth)
        with self.assertRaisesRegex(ArenaError, "objective proof"):
            self.arena.submit_ranked_result(
                operator="child-op",
                job_id=job,
                version_id=self.child,
                result_hash="correct",
                proof_id="proof",
                objective_proof_valid=False,
            )

    def test_job_authorization_is_single_use(self) -> None:
        self.arena.fund_commons("founder", 20_000)
        auth = self.arena.authorize_ranked_job(
            spec_hash="spec",
            verifier_id="v",
            reward=10_000,
            deadline=self.arena.now + 100,
            expected_result_hash="correct",
            verified_cost=0,
            cost_recipient=None,
        )
        self.arena.create_ranked_job(auth)
        with self.assertRaisesRegex(ArenaError, "authorization replay"):
            self.arena.create_ranked_job(auth)

    def test_global_proof_replay_is_rejected(self) -> None:
        self.arena.fund_commons("founder", 20_000)
        proof_id = "same-proof"
        for index in range(2):
            auth = self.arena.authorize_ranked_job(
                spec_hash=f"spec-{index}",
                verifier_id="v",
                reward=10_000,
                deadline=self.arena.now + 100,
                expected_result_hash=f"correct-{index}",
                verified_cost=0,
                cost_recipient=None,
            )
            job = self.arena.create_ranked_job(auth)
            if index == 0:
                self.arena.submit_ranked_result(
                    operator="child-op",
                    job_id=job,
                    version_id=self.child,
                    result_hash="correct-0",
                    proof_id=proof_id,
                    objective_proof_valid=True,
                )
            else:
                with self.assertRaisesRegex(ArenaError, "proof replay"):
                    self.arena.submit_ranked_result(
                        operator="child-op",
                        job_id=job,
                        version_id=self.child,
                        result_hash="correct-1",
                        proof_id=proof_id,
                        objective_proof_valid=True,
                    )

    def test_verified_cost_requires_vault_capital(self) -> None:
        self.arena.fund_commons("founder", 10_000)
        auth = self.arena.authorize_ranked_job(
            spec_hash="spec",
            verifier_id="v",
            reward=10_000,
            deadline=self.arena.now + 100,
            expected_result_hash="correct",
            verified_cost=1,
            cost_recipient="provider",
        )
        job = self.arena.create_ranked_job(auth)
        with self.assertRaisesRegex(ArenaError, "insufficient vault"):
            self.arena.submit_ranked_result(
                operator="child-op",
                job_id=job,
                version_id=self.child,
                result_hash="correct",
                proof_id="proof",
                objective_proof_valid=True,
            )

    def test_expired_ranked_reward_returns_to_commons(self) -> None:
        self.arena.fund_commons("founder", 10_000)
        auth = self.arena.authorize_ranked_job(
            spec_hash="spec",
            verifier_id="v",
            reward=10_000,
            deadline=self.arena.now + 10,
            expected_result_hash="correct",
            verified_cost=0,
            cost_recipient=None,
        )
        job = self.arena.create_ranked_job(auth)
        self.arena.advance(11)
        self.arena.expire_ranked_job(job)
        self.assertEqual(self.arena.ranked_jobs[job].status, RankedJobStatus.EXPIRED)
        # v0.2.0: commons holds the 10_000 reward + 2 registration bonds.
        self.assertEqual(self.arena.commons_available, 10_000 + 2 * self.arena.VERSION_BOND)
        self.assertEqual(self.arena.commons_reserved, 0)
        self.arena.assert_invariants()

    def test_strictly_more_profitable_child_supersedes_and_inherits(self) -> None:
        self.arena.donate("donor", self.root, 200_000)
        _, epoch = self._ranked_job(
            name="root-job", reward=50_000, cost=20_000, version_id=self.root, operator="root-op"
        )
        self._ranked_job(
            name="child-job", reward=100_000, cost=10_000, version_id=self.child, operator="child-op"
        )
        root_before = self.arena.vaults[self.root]
        child_before = self.arena.vaults[self.child]
        self.arena.advance_to_next_epoch()
        self.arena.heartbeat(operator="child-op", version_id=self.child, state_hash="state", runtime_attested=True)
        transferred = self.arena.supersede(challenger_id=self.child, epoch=epoch)
        self.assertEqual(transferred, root_before)
        self.assertEqual(self.arena.vaults[self.root], 0)
        # v0.2.0: heartbeat burn reduces child vault by 1 unit.
        self.assertEqual(self.arena.vaults[self.child], child_before + root_before - self.arena.HEARTBEAT_BURN)
        self.assertEqual(self.arena.versions[self.root].status, VersionStatus.SUPERSEDED)
        self.assertEqual(self.arena.versions[self.root].successor, self.child)
        self.assertEqual(self.arena.versions[self.child].status, VersionStatus.ACTIVE)
        self.assertEqual(self.arena.active_version[self.lineage], self.child)
        self.arena.assert_invariants()


    def test_nonpositive_challenger_cannot_replace_a_worse_incumbent(self) -> None:
        _, epoch = self._ranked_job(
            name="root-loss",
            reward=10_000,
            cost=20_000,
            version_id=self.root,
            operator="root-op",
        )
        self._ranked_job(
            name="child-smaller-loss",
            reward=10_000,
            cost=15_000,
            version_id=self.child,
            operator="child-op",
        )
        self.assertGreater(self.arena.profit(self.child, epoch), self.arena.profit(self.root, epoch))
        self.assertLess(self.arena.profit(self.child, epoch), 0)
        self.arena.advance_to_next_epoch()
        self.arena.heartbeat(
            operator="child-op",
            version_id=self.child,
            state_hash="still-loss-making",
            runtime_attested=True,
        )
        with self.assertRaisesRegex(ArenaError, "positive ranked profit"):
            self.arena.supersede(challenger_id=self.child, epoch=epoch)

    def test_direct_token_transfer_can_only_be_absorbed_into_commons(self) -> None:
        epoch = self.arena.current_epoch()
        before = self.arena.wallets["whale"]
        self.arena.direct_transfer_to_arena("whale", 123_000)
        self.assertEqual(self.arena.unaccounted_surplus, 123_000)
        self.assertEqual(self.arena.profit(self.child, epoch), 0)
        absorbed = self.arena.absorb_surplus()
        self.assertEqual(absorbed, 123_000)
        # v0.2.0: commons also holds 2 bonds (root + child) = 2000.
        self.assertEqual(self.arena.commons_available, 123_000 + 2 * self.arena.VERSION_BOND)
        self.assertEqual(self.arena.wallets["whale"], before - 123_000)
        self.assertEqual(self.arena.profit(self.child, epoch), 0)
        self.arena.assert_invariants()

    def test_lower_profit_cannot_supersede(self) -> None:
        _, epoch = self._ranked_job(
            name="root-high", reward=100_000, cost=0, version_id=self.root, operator="root-op"
        )
        self._ranked_job(
            name="child-low", reward=20_000, cost=0, version_id=self.child, operator="child-op"
        )
        self.arena.advance_to_next_epoch()
        self.arena.heartbeat(operator="child-op", version_id=self.child, state_hash="state", runtime_attested=True)
        with self.assertRaisesRegex(ArenaError, "not strictly more profitable"):
            self.arena.supersede(challenger_id=self.child, epoch=epoch)

    def test_equal_profit_cannot_supersede(self) -> None:
        _, epoch = self._ranked_job(
            name="root-equal", reward=50_000, cost=0, version_id=self.root, operator="root-op"
        )
        self._ranked_job(
            name="child-equal", reward=50_000, cost=0, version_id=self.child, operator="child-op"
        )
        self.arena.advance_to_next_epoch()
        self.arena.heartbeat(operator="child-op", version_id=self.child, state_hash="state", runtime_attested=True)
        with self.assertRaisesRegex(ArenaError, "not strictly more profitable"):
            self.arena.supersede(challenger_id=self.child, epoch=epoch)

    def test_challenge_requires_last_closed_epoch(self) -> None:
        _, epoch = self._ranked_job(
            name="child-only", reward=10_000, cost=0, version_id=self.child, operator="child-op"
        )
        with self.assertRaisesRegex(ArenaError, "wrong comparison epoch"):
            self.arena.supersede(challenger_id=self.child, epoch=epoch)

    def test_heartbeat_requires_live_runtime_attestation(self) -> None:
        before = self.arena.versions[self.child].last_heartbeat
        self.arena.advance(10)
        with self.assertRaisesRegex(ArenaError, "runtime heartbeat"):
            self.arena.heartbeat(
                operator="child-op",
                version_id=self.child,
                state_hash="state",
                runtime_attested=False,
            )
        self.assertEqual(self.arena.versions[self.child].last_heartbeat, before)

    def test_recent_heartbeat_is_required_for_ranked_work(self) -> None:
        self.arena.advance(self.arena.HEARTBEAT_GRACE + 1)
        self.arena.fund_commons("founder", 10_000)
        auth = self.arena.authorize_ranked_job(
            spec_hash="spec",
            verifier_id="v",
            reward=10_000,
            deadline=self.arena.now + 100,
            expected_result_hash="correct",
            verified_cost=0,
            cost_recipient=None,
        )
        job = self.arena.create_ranked_job(auth)
        with self.assertRaisesRegex(ArenaError, "heartbeat too old"):
            self.arena.submit_ranked_result(
                operator="child-op",
                job_id=job,
                version_id=self.child,
                result_hash="correct",
                proof_id="proof",
                objective_proof_valid=True,
            )

    def test_stale_ejection_moves_locked_capital_to_commons(self) -> None:
        self.arena.donate("donor", self.root, 123_456)
        self.arena.advance(self.arena.STALE_AFTER + 1)
        moved = self.arena.eject_stale(self.root)
        self.assertEqual(moved, 123_456)
        self.assertEqual(self.arena.vaults[self.root], 0)
        # v0.2.0: commons also holds 2 bonds (root + child) = 2000 added.
        self.assertEqual(self.arena.commons_available, 123_456 + 2 * self.arena.VERSION_BOND)
        self.assertEqual(self.arena.versions[self.root].status, VersionStatus.STALE)
        self.assertIsNone(self.arena.active_version[self.lineage])
        self.arena.assert_invariants()

    def test_profitable_candidate_can_claim_vacancy(self) -> None:
        # Let the incumbent age, then create a fresh candidate in the current epoch.
        self.arena.advance(self.arena.STALE_AFTER + 1)
        self.arena.mint("fresh-op", 2_000_000)  # v0.2.0: bond funding
        fresh = self.arena.register_version(
            lineage_id=self.lineage,
            parent_id=self.root,
            operator="fresh-op",
            declaration=self.arena.declaration("fresh"),
            salt="fresh",
            runtime_attested=True,
        )
        _, epoch = self._ranked_job(
            name="fresh-job", reward=50_000, cost=0, version_id=fresh, operator="fresh-op"
        )
        self.arena.advance_to_next_epoch()
        self.arena.heartbeat(operator="fresh-op", version_id=fresh, state_hash="state", runtime_attested=True)
        self.arena.eject_stale(self.root)
        self.arena.claim_vacancy(version_id=fresh, epoch=epoch)
        self.assertEqual(self.arena.active_version[self.lineage], fresh)
        self.assertEqual(self.arena.versions[fresh].status, VersionStatus.ACTIVE)

    def test_successor_can_finish_market_job_opened_for_incumbent(self) -> None:
        job = self.arena.open_market_job(
            buyer="buyer",
            target_version=self.root,
            spec_hash="market-handover",
            reward=10_000,
            deadline=self.arena.now + 1_000_000,
        )
        _, epoch = self._ranked_job(
            name="handover-winner", reward=100_000, cost=0,
            version_id=self.child, operator="child-op",
        )
        self.arena.advance_to_next_epoch()
        self.arena.heartbeat(
            operator="child-op", version_id=self.child, state_hash="state",
            runtime_attested=True,
        )
        self.arena.supersede(challenger_id=self.child, epoch=epoch)
        self.arena.submit_market_result(
            operator="child-op", job_id=job, result_hash="successor-result"
        )
        self.assertEqual(self.arena.market_jobs[job].performer_version, self.child)
        beneficiary = self.arena.accept_market_result(buyer="buyer", job_id=job)
        self.assertEqual(beneficiary, self.child)
        self.arena.assert_invariants()

    def test_market_payment_to_superseded_version_routes_to_successor(self) -> None:
        job = self.arena.open_market_job(
            buyer="buyer",
            target_version=self.root,
            spec_hash="market",
            reward=10_000,
            deadline=self.arena.now + 1_000_000,
        )
        self.arena.submit_market_result(operator="root-op", job_id=job, result_hash="result")
        _, epoch = self._ranked_job(
            name="child-wins", reward=100_000, cost=0, version_id=self.child, operator="child-op"
        )
        self.arena.advance_to_next_epoch()
        self.arena.heartbeat(operator="child-op", version_id=self.child, state_hash="state", runtime_attested=True)
        self.arena.supersede(challenger_id=self.child, epoch=epoch)
        beneficiary = self.arena.accept_market_result(buyer="buyer", job_id=job)
        self.assertEqual(beneficiary, self.child)
        self.assertEqual(self.arena.market_revenue[self.child], 10_000)
        self.arena.assert_invariants()

    def test_market_refund_after_deadline(self) -> None:
        before = self.arena.wallets["buyer"]
        job = self.arena.open_market_job(
            buyer="buyer",
            target_version=self.child,
            spec_hash="market",
            reward=10_000,
            deadline=self.arena.now + 10,
        )
        self.arena.advance(11)
        self.arena.refund_market_job(buyer="buyer", job_id=job)
        self.assertEqual(self.arena.market_jobs[job].status, MarketJobStatus.REFUNDED)
        self.assertEqual(self.arena.wallets["buyer"], before)
        self.arena.assert_invariants()

    def test_operating_expense_requires_provider_proof_and_is_replay_safe(self) -> None:
        self.arena.donate("donor", self.child, 10_000)
        kwargs = dict(
            operator="child-op",
            version_id=self.child,
            expense_id="openrouter-1",
            recipient="provider",
            amount=1_000,
            payload_hash="usage-hash",
            proof_id="provider-receipt-1",
        )
        with self.assertRaisesRegex(ArenaError, "invalid expense proof"):
            self.arena.settle_operating_expense(**kwargs, valid_provider_proof=False)
        self.arena.settle_operating_expense(**kwargs, valid_provider_proof=True)
        with self.assertRaisesRegex(ArenaError, "proof replay"):
            self.arena.settle_operating_expense(**kwargs, valid_provider_proof=True)
        self.assertEqual(self.arena.operating_spent[self.child], 1_000)
        self.arena.assert_invariants()

    def test_operator_cannot_invent_an_arbitrary_withdrawal(self) -> None:
        self.assertFalse(hasattr(self.arena, "withdraw"))
        self.assertFalse(hasattr(self.arena, "halt"))

    def test_non_agpl_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(ArenaError, "AGPL"):
            self.arena.register_version(
                lineage_id=self.lineage,
                parent_id=self.root,
                operator="closed-op",
                declaration=self.arena.declaration("closed"),
                salt="closed",
                runtime_attested=True,
                license_id="proprietary",
            )


    def test_non_ipfs_source_uri_is_rejected(self) -> None:
        with self.assertRaisesRegex(ArenaError, "IPFS"):
            self.arena.register_version(
                lineage_id=self.lineage,
                parent_id=self.root,
                operator="http-op",
                declaration=self.arena.declaration(
                    "http-source", source_uri="https://example.invalid/source.tar.gz"
                ),
                salt="http-source",
                runtime_attested=True,
            )

    def test_nonpositive_ranked_profit_does_not_reset_stale_clock(self) -> None:
        self.arena.advance(self.arena.STALE_AFTER - 100)
        # v0.2.0: heartbeat requires burn from vault; pre-fund root.
        self.arena.donate("donor", self.root, 1_000)
        self.arena.heartbeat(
            operator="root-op",
            version_id=self.root,
            state_hash="near-stale",
            runtime_attested=True,
        )
        self._ranked_job(
            name="loss-making",
            reward=10_000,
            cost=20_000,
            version_id=self.root,
            operator="root-op",
        )
        self.assertIsNone(self.arena.versions[self.root].last_positive_profit_at)
        self.arena.advance(101)
        moved = self.arena.eject_stale(self.root)
        self.assertGreaterEqual(moved, 0)
        self.assertEqual(self.arena.versions[self.root].status, VersionStatus.STALE)

    def test_positive_ranked_profit_resets_stale_clock(self) -> None:
        self.arena.advance(self.arena.STALE_AFTER - 100)
        # v0.2.0: heartbeat requires burn from vault; pre-fund root.
        self.arena.donate("donor", self.root, 1_000)
        self.arena.heartbeat(
            operator="root-op",
            version_id=self.root,
            state_hash="near-stale",
            runtime_attested=True,
        )
        self._ranked_job(
            name="profitable-refresh",
            reward=10_000,
            cost=1_000,
            version_id=self.root,
            operator="root-op",
        )
        refreshed = self.arena.versions[self.root].last_positive_profit_at
        self.assertEqual(refreshed, self.arena.now)
        self.arena.advance(101)
        with self.assertRaisesRegex(ArenaError, "not stale"):
            self.arena.eject_stale(self.root)

    def test_empty_market_result_is_rejected(self) -> None:
        job = self.arena.open_market_job(
            buyer="buyer",
            target_version=self.child,
            spec_hash="market-empty",
            reward=1_000,
            deadline=self.arena.now + 100,
        )
        with self.assertRaisesRegex(ArenaError, "result hash"):
            self.arena.submit_market_result(operator="child-op", job_id=job, result_hash="")

    def test_runtime_attestation_is_required(self) -> None:
        with self.assertRaisesRegex(ArenaError, "runtime attestation"):
            self.arena.register_version(
                lineage_id=self.lineage,
                parent_id=self.root,
                operator="fake-op",
                declaration=self.arena.declaration("fake"),
                salt="fake",
                runtime_attested=False,
            )

    def test_parent_must_belong_to_lineage(self) -> None:
        self.arena.mint("other-op", 2_000_000)  # v0.2.0: bond funding
        other_lineage, other_root = self.arena.create_lineage(
            operator="other-op",
            declaration=self.arena.declaration("other-root"),
            salt="other",
            runtime_attested=True,
            bond_funder="other-op",
        )
        self.assertNotEqual(other_lineage, self.lineage)
        with self.assertRaisesRegex(ArenaError, "parent lineage mismatch"):
            self.arena.register_version(
                lineage_id=self.lineage,
                parent_id=other_root,
                operator="bad-op",
                declaration=self.arena.declaration("bad"),
                salt="bad",
                runtime_attested=True,
            )

    def test_top_three_is_routing_not_survival(self) -> None:
        versions = [self.root, self.child]
        operators = ["root-op", "child-op"]
        for index in range(4):
            self.arena.mint(f"op-{index}", 2_000_000)  # v0.2.0: bond funding
            version = self.arena.register_version(
                lineage_id=self.lineage,
                parent_id=self.root,
                operator=f"op-{index}",
                declaration=self.arena.declaration(f"v-{index}"),
                salt=f"salt-{index}",
                runtime_attested=True,
                bond_funder=f"op-{index}",
            )
            versions.append(version)
            operators.append(f"op-{index}")
        epoch = self.arena.current_epoch()
        for index, (version, operator) in enumerate(zip(versions, operators), start=1):
            self._ranked_job(
                name=f"rank-{index}",
                reward=index * 10_000,
                cost=0,
                version_id=version,
                operator=operator,
            )
        top = self.arena.top_versions(lineage_id=self.lineage, epoch=epoch)
        self.assertEqual(len(top), 3)
        self.assertEqual([self.arena.profit(v, epoch) for v in top], [60_000, 50_000, 40_000])
        live_count = sum(1 for _ in self.arena.live_versions(self.lineage))
        self.assertEqual(live_count, 6)

    def test_token_conservation_through_mixed_flow(self) -> None:
        self.arena.donate("donor", self.child, 30_000)
        self._ranked_job(
            name="mixed", reward=20_000, cost=5_000, version_id=self.child, operator="child-op"
        )
        market = self.arena.open_market_job(
            buyer="buyer",
            target_version=self.child,
            spec_hash="market",
            reward=7_000,
            deadline=self.arena.now + 100,
        )
        self.arena.submit_market_result(operator="child-op", job_id=market, result_hash="r")
        self.arena.accept_market_result(buyer="buyer", job_id=market)
        self.arena.settle_operating_expense(
            operator="child-op",
            version_id=self.child,
            expense_id="bill",
            recipient="provider",
            amount=2_000,
            payload_hash="p",
            proof_id="bill-proof",
            valid_provider_proof=True,
        )
        self.arena.assert_invariants()
        self.assertEqual(self.arena.conservation_total(), self.arena.total_minted)


if __name__ == "__main__":
    unittest.main()
