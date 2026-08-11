#!/usr/bin/env python3
"""Run a complete dependency-free EOH Arena selection cycle."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.arena import Arena


def settle(arena: Arena, *, name: str, reward: int, cost: int, version: str, operator: str) -> int:
    arena.fund_commons("commons-funder", reward)
    if cost:
        arena.donate("cost-funder", version, cost)
    result = arena._hash("result", name)
    authorization = arena.authorize_ranked_job(
        spec_hash=arena._hash("spec", name),
        verifier_id="objective-fixed-hash",
        reward=reward,
        deadline=arena.now + 3_600,
        expected_result_hash=result,
        verified_cost=cost,
        cost_recipient="provider" if cost else None,
    )
    job = arena.create_ranked_job(authorization)
    epoch = arena.current_epoch()
    arena.submit_ranked_result(
        operator=operator,
        job_id=job,
        version_id=version,
        result_hash=result,
        proof_id=arena._hash("proof", job, version),
        objective_proof_valid=True,
    )
    return epoch


def main() -> None:
    arena = Arena()
    for account in ("commons-funder", "cost-funder", "whale", "provider",
                    "incumbent-op", "challenger-op"):
        arena.mint(account, 10_000_000)

    lineage, incumbent = arena.create_lineage(
        operator="incumbent-op",
        declaration=arena.declaration("incumbent"),
        salt="root",
        runtime_attested=True,
        bond_funder="incumbent-op",
    )
    challenger = arena.register_version(
        lineage_id=lineage,
        parent_id=incumbent,
        operator="challenger-op",
        declaration=arena.declaration("challenger"),
        salt="fork",
        runtime_attested=True,
        bond_funder="challenger-op",
    )

    # A whale can keep a version alive, but cannot purchase rank.
    arena.donate("whale", incumbent, 1_000_000)

    epoch = settle(
        arena,
        name="incumbent-job",
        reward=100_000,
        cost=40_000,
        version=incumbent,
        operator="incumbent-op",
    )
    settle(
        arena,
        name="challenger-job",
        reward=130_000,
        cost=20_000,
        version=challenger,
        operator="challenger-op",
    )

    before = {
        "incumbent_profit": arena.profit(incumbent, epoch),
        "challenger_profit": arena.profit(challenger, epoch),
        "incumbent_vault": arena.vaults[incumbent],
        "challenger_vault": arena.vaults[challenger],
    }

    arena.advance_to_next_epoch()
    arena.heartbeat(
        operator="challenger-op",
        version_id=challenger,
        state_hash=arena._hash("state", challenger, arena.now),
        runtime_attested=True,
    )
    transferred = arena.supersede(challenger_id=challenger, epoch=epoch)
    arena.assert_invariants()

    print(
        json.dumps(
            {
                "lineage": lineage,
                "epoch": epoch,
                "before": before,
                "selection": {
                    "winner": challenger,
                    "capital_transferred": transferred,
                    "incumbent_status": arena.versions[incumbent].status.value,
                    "challenger_status": arena.versions[challenger].status.value,
                    "winner_vault": arena.vaults[challenger],
                },
                "invariant": "token conservation holds",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
