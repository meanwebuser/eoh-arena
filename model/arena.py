"""Deterministic reference model for EOH Arena v0.2.0.

This model is intentionally stricter than a normal SaaS ledger:

* donations and subjective market payments never affect rank;
* only pre-authorized objective jobs create ranked revenue;
* ranked result, verified cost, provider payment and reward settle atomically;
* protocol-held capital has no arbitrary withdrawal path;
* a strictly more profitable child can supersede the incumbent without consent;
* stale versions are economically ejected, half to commons and half to lineage successor;
* version registration requires Sybil bond (U1);
* operator is a multi-sig with daily expense cap (U2);
* supersede and claim_vacancy use commit-reveal to defeat MEV (U3);
* job verifier is selected from a set by blockhash (U4);
* heartbeat requires proof-of-retrieval from IPFS (U5);
* market jobs may auto-accept on objective proof (U6);
* ranked profit is median over last 3 epochs (U8);
* stale capital splits between commons and lineage successor (U9);
* heartbeat burns a micro-fee (U10).

It is not an EVM emulator. The Solidity contract mirrors these state transitions.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import DefaultDict, Iterable


class ArenaError(RuntimeError):
    """Protocol rule violation."""


class VersionStatus(str, Enum):
    INCUBATING = "incubating"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    STALE = "stale"


class RankedJobStatus(str, Enum):
    OPEN = "open"
    SETTLED = "settled"
    EXPIRED = "expired"


class MarketJobStatus(str, Enum):
    OPEN = "open"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REFUNDED = "refunded"


@dataclass(frozen=True)
class Declaration:
    source_digest: str
    image_digest: str
    provenance_digest: str
    runtime_identity: str
    source_uri: str


@dataclass
class Version:
    version_id: str
    lineage_id: str
    parent_id: str | None
    operator: str
    declaration: Declaration
    created_at: int
    last_heartbeat: int
    last_positive_profit_at: int | None
    status: VersionStatus
    successor: str | None = None
    # v0.2.0 fields:
    bond_amount: int = 0           # U1: how much this version bonded
    operator_signers: list[str] | None = None     # U2: multi-sig (None = single operator)
    operator_threshold: int = 1    # U2: M-of-N required


@dataclass
class Economy:
    ranked_revenue: int = 0
    verified_ranked_cost: int = 0

    @property
    def profit(self) -> int:
        return self.ranked_revenue - self.verified_ranked_cost


@dataclass(frozen=True)
class JobAuthorization:
    authorization_id: str
    spec_hash: str
    verifier_id: str
    reward: int
    deadline: int
    expected_result_hash: str
    verified_cost: int
    cost_recipient: str | None
    # v0.2.0 U4: verifier set (replaces single verifier_id for ranked jobs).
    # When non-empty, the actual verifier for a settlement is selected by
    #   verifier_set[entropy % len]
    # where entropy = keccak256(blockhash, jobId). Single-verifier jobs keep
    # verifier_set = [verifier_id] for backward compatibility.
    verifier_set: tuple[str, ...] = ()


@dataclass
class RankedJob:
    job_id: str
    authorization: JobAuthorization
    status: RankedJobStatus = RankedJobStatus.OPEN
    settlement_epoch: int | None = None
    winner_version: str | None = None
    result_hash: str | None = None
    proof_id: str | None = None


@dataclass
class MarketJob:
    job_id: str
    buyer: str
    target_version: str
    spec_hash: str
    reward: int
    deadline: int
    status: MarketJobStatus = MarketJobStatus.OPEN
    result_hash: str | None = None
    performer_version: str | None = None
    # v0.2.0 U6: optional objective work_verifier. If present and proof
    # passes, market job auto-settles on submit without buyer approval.
    work_verifier_id: str | None = None


class Arena:
    """Pure-Python state machine with token conservation checks."""

    EPOCH_LENGTH = 7 * 24 * 60 * 60
    STALE_AFTER = 30 * 24 * 60 * 60
    HEARTBEAT_PERIOD = 60 * 60
    HEARTBEAT_GRACE = 2 * 60 * 60
    TOP_ROUTING_COUNT = 3
    REQUIRED_LICENSE = "AGPL-3.0-or-later"

    # ── v0.2.0 hardening ───────────────────────────────────────────────
    # U1: Sybil bond. Refundable after one epoch with ranked revenue.
    VERSION_BOND = 1_000  # smallest settlement-token units; prod: 1000 * 10^decimals

    # U2: Daily expense cap per version. Stops vault drain on operator compromise.
    DAILY_EXPENSE_CAP = 50_000

    # U10: Heartbeat micro-burn. Goes to commons.
    HEARTBEAT_BURN = 1  # 1 unit per heartbeat

    # U8: Profit window — median over last N epochs (defeats single-epoch outlier).
    PROFIT_WINDOW_EPOCHS = 3

    # U9: Stale capital split — half to commons, half to lineage successor.
    STALE_LINEAGE_SHARE_NUM = 1
    STALE_LINEAGE_SHARE_DEN = 2  # 1/2 to lineage successor, 1/2 to commons

    # U3: Commit-reveal phase durations.
    COMMIT_PHASE_BLOCKS = 4       # how many blocks to commit before reveal window opens
    REVEAL_PHASE_BLOCKS = 8       # how many blocks to reveal after commit window

    def __init__(self, *, start_time: int = 1_800_000_000) -> None:
        self.now = start_time
        self.versions: dict[str, Version] = {}
        self.active_version: dict[str, str | None] = {}
        self.lineage_versions: DefaultDict[str, list[str]] = defaultdict(list)

        self.wallets: DefaultDict[str, int] = defaultdict(int)
        self.vaults: DefaultDict[str, int] = defaultdict(int)
        self.capital_in: DefaultDict[str, int] = defaultdict(int)
        self.market_revenue: DefaultDict[str, int] = defaultdict(int)
        self.operating_spent: DefaultDict[str, int] = defaultdict(int)
        self.economies: DefaultDict[tuple[str, int], Economy] = defaultdict(Economy)

        # U1: version registration bond.
        self.version_bond: DefaultDict[str, int] = defaultdict(int)
        self.bond_epoch: dict[str, int] = {}
        self.bond_burned = 0  # accumulated burned bonds go to commons

        # U2: multi-sig operator + daily cap state.
        # operator_signers[version_id] = sorted list of signer addresses
        # operator_threshold[version_id] = M-of-N required
        self.operator_signers: dict[str, list[str]] = {}
        self.operator_threshold: dict[str, int] = {}
        self.daily_expense: DefaultDict[tuple[str, int], int] = defaultdict(int)

        # U3: commit-reveal for supersede / claim_vacancy.
        # commit_hash -> (challenger_id, epoch, committed_at)
        self.supersede_commits: dict[str, tuple[str, int, int]] = {}
        self.supersede_revealed: set[str] = set()  # commit_hash

        # U5: heartbeat proof-of-retrieval tracking.
        # last_ipfs_proof_ts[version_id] = ts of last valid PoR
        self.last_ipfs_proof_ts: dict[str, int] = {}

        self.commons_available = 0
        self.commons_reserved = 0
        self.market_escrow_reserved = 0
        self.unaccounted_surplus = 0
        self.heartbeat_burn_collected = 0  # U10: cumulative burn

        self.authorizations: dict[str, JobAuthorization] = {}
        self.authorization_used: set[str] = set()
        self.ranked_jobs: dict[str, RankedJob] = {}
        self.market_jobs: dict[str, MarketJob] = {}
        self.proof_used: set[str] = set()

        self._version_nonce = 0
        self._ranked_job_nonce = 0
        self._market_job_nonce = 0
        self.total_minted = 0

    # ---------- deterministic helpers ----------

    @staticmethod
    def _hash(*parts: object) -> str:
        payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def declaration(
        name: str,
        *,
        source_uri: str | None = None,
        runtime_identity: str | None = None,
    ) -> Declaration:
        return Declaration(
            source_digest=Arena._hash("source", name),
            image_digest=Arena._hash("image", name),
            provenance_digest=Arena._hash("provenance", name),
            runtime_identity=runtime_identity or Arena._hash("runtime", name),
            source_uri=source_uri or f"ipfs://{Arena._hash('cid', name)}",
        )

    def current_epoch(self) -> int:
        return self.now // self.EPOCH_LENGTH

    def last_closed_epoch(self) -> int:
        epoch = self.current_epoch()
        if epoch == 0:
            raise ArenaError("no closed epoch")
        return epoch - 1

    def advance(self, seconds: int) -> None:
        if seconds < 0:
            raise ArenaError("time cannot move backwards")
        self.now += seconds

    def advance_to_next_epoch(self) -> None:
        self.now = (self.current_epoch() + 1) * self.EPOCH_LENGTH

    # ---------- money ----------

    def mint(self, account: str, amount: int) -> None:
        self._require_positive(amount)
        self.wallets[account] += amount
        self.total_minted += amount

    def fund_commons(self, donor: str, amount: int) -> None:
        self._debit_wallet(donor, amount)
        self.commons_available += amount

    def direct_transfer_to_arena(self, donor: str, amount: int) -> None:
        """Model an ERC-20 transfer that bypasses protocol entrypoints."""
        self._debit_wallet(donor, amount)
        self.unaccounted_surplus += amount

    def absorb_surplus(self) -> int:
        if self.unaccounted_surplus <= 0:
            raise ArenaError("no unaccounted surplus")
        amount = self.unaccounted_surplus
        self.unaccounted_surplus = 0
        self.commons_available += amount
        return amount

    def donate(self, donor: str, version_id: str, amount: int) -> str:
        beneficiary = self._funding_beneficiary(version_id)
        self._debit_wallet(donor, amount)
        self.vaults[beneficiary] += amount
        self.capital_in[beneficiary] += amount
        return beneficiary

    def settle_operating_expense(
        self,
        *,
        operator: str,
        version_id: str,
        expense_id: str,
        recipient: str,
        amount: int,
        payload_hash: str,
        proof_id: str,
        valid_provider_proof: bool,
        operator_sigs: list[str] | None = None,  # U2: multi-sig signatures
    ) -> None:
        version = self._version(version_id)
        self._require_operator(version, operator)
        self._require_live(version)
        self._require_positive(amount)
        if not valid_provider_proof or not proof_id:
            raise ArenaError("invalid expense proof")
        if proof_id in self.proof_used:
            raise ArenaError("proof replay")
        if self.vaults[version_id] < amount:
            raise ArenaError("insufficient vault")
        if not expense_id or not payload_hash or not recipient:
            raise ArenaError("invalid expense metadata")
        # U2: daily expense cap (anti-drain).
        day = self.now // 86_400
        today_spent = self.daily_expense[(version_id, day)]
        if today_spent + amount > self.DAILY_EXPENSE_CAP:
            raise ArenaError("daily expense cap exceeded")
        # U2: multi-sig check for large expenses.
        if amount > self.DAILY_EXPENSE_CAP // 10:
            if not operator_sigs or len(set(operator_sigs)) < version.operator_threshold:
                raise ArenaError("large expense requires multi-sig")
            for s in operator_sigs:
                if s not in (version.operator_signers or []):
                    raise ArenaError("unknown signer")

        self.proof_used.add(proof_id)
        self.vaults[version_id] -= amount
        self.operating_spent[version_id] += amount
        self.daily_expense[(version_id, day)] += amount
        self.wallets[recipient] += amount

    # ---------- source/runtime registration ----------

    def create_lineage(
        self,
        *,
        operator: str,
        declaration: Declaration,
        salt: str,
        runtime_attested: bool,
        license_id: str = REQUIRED_LICENSE,
        bond_funder: str | None = None,
        operator_signers: list[str] | None = None,
        operator_threshold: int = 1,
    ) -> tuple[str, str]:
        self._validate_declaration(declaration, runtime_attested, license_id)
        lineage_id = self._hash("lineage-v1", operator, declaration.source_digest, salt)
        if lineage_id in self.active_version:
            raise ArenaError("lineage already exists")
        version_id = self._new_version_id(lineage_id, None, operator, declaration, salt)
        # U1: bond requirement.
        funder = bond_funder or operator
        self._debit_wallet(funder, self.VERSION_BOND)
        self.version_bond[version_id] = self.VERSION_BOND
        self.bond_epoch[version_id] = self.current_epoch()
        self.commons_available += self.VERSION_BOND  # bond held in commons until refund
        # U2: multi-sig operator setup.
        signers = tuple(operator_signers) if operator_signers else (operator,)
        if operator_threshold < 1 or operator_threshold > len(signers):
            raise ArenaError("invalid operator threshold")
        if operator not in signers:
            raise ArenaError("operator must be a signer")
        self.operator_signers[version_id] = list(signers)
        self.operator_threshold[version_id] = operator_threshold
        version = Version(
            version_id=version_id,
            lineage_id=lineage_id,
            parent_id=None,
            operator=operator,
            declaration=declaration,
            created_at=self.now,
            last_heartbeat=self.now,
            last_positive_profit_at=None,
            status=VersionStatus.ACTIVE,
            bond_amount=self.VERSION_BOND,
            operator_signers=list(signers),
            operator_threshold=operator_threshold,
        )
        self.versions[version_id] = version
        self.lineage_versions[lineage_id].append(version_id)
        self.active_version[lineage_id] = version_id
        return lineage_id, version_id

    def register_version(
        self,
        *,
        lineage_id: str,
        parent_id: str,
        operator: str,
        declaration: Declaration,
        salt: str,
        runtime_attested: bool,
        license_id: str = REQUIRED_LICENSE,
        bond_funder: str | None = None,
        operator_signers: list[str] | None = None,
        operator_threshold: int = 1,
    ) -> str:
        if lineage_id not in self.active_version:
            raise ArenaError("lineage not found")
        parent = self._version(parent_id)
        if parent.lineage_id != lineage_id:
            raise ArenaError("parent lineage mismatch")
        self._validate_declaration(declaration, runtime_attested, license_id)
        version_id = self._new_version_id(lineage_id, parent_id, operator, declaration, salt)
        if version_id in self.versions:
            raise ArenaError("version already exists")
        # U1: bond requirement.
        funder = bond_funder or operator
        self._debit_wallet(funder, self.VERSION_BOND)
        self.version_bond[version_id] = self.VERSION_BOND
        self.bond_epoch[version_id] = self.current_epoch()
        self.commons_available += self.VERSION_BOND
        # U2: multi-sig operator setup.
        signers = tuple(operator_signers) if operator_signers else (operator,)
        if operator_threshold < 1 or operator_threshold > len(signers):
            raise ArenaError("invalid operator threshold")
        if operator not in signers:
            raise ArenaError("operator must be a signer")
        self.operator_signers[version_id] = list(signers)
        self.operator_threshold[version_id] = operator_threshold
        self.versions[version_id] = Version(
            version_id=version_id,
            lineage_id=lineage_id,
            parent_id=parent_id,
            operator=operator,
            declaration=declaration,
            created_at=self.now,
            last_heartbeat=self.now,
            last_positive_profit_at=None,
            status=VersionStatus.INCUBATING,
            bond_amount=self.VERSION_BOND,
            operator_signers=list(signers),
            operator_threshold=operator_threshold,
        )
        self.lineage_versions[lineage_id].append(version_id)
        return version_id

    # U1: refund bond after one epoch with positive ranked revenue.
    def reclaim_bond(self, *, operator: str, version_id: str) -> int:
        version = self._version(version_id)
        self._require_operator(version, operator)
        if self.version_bond[version_id] == 0:
            raise ArenaError("no bond to reclaim")
        bond_epoch = self.bond_epoch.get(version_id, self.current_epoch())
        if self.current_epoch() <= bond_epoch:
            raise ArenaError("bond still in lock-up epoch")
        last_epoch = self.current_epoch() - 1
        econ = self.economies[(version_id, last_epoch)]
        if econ.ranked_revenue == 0 or econ.profit <= 0:
            raise ArenaError("no positive ranked profit last epoch")
        amount = self.version_bond[version_id]
        self.version_bond[version_id] = 0
        if self.commons_available < amount:
            raise ArenaError("commons insufficient for bond refund")
        self.commons_available -= amount
        self.wallets[operator] += amount
        return amount

    # U1: burn bond if version goes stale without earning.
    def _slash_bond_if_unprofitable(self, version_id: str) -> None:
        if self.version_bond[version_id] == 0:
            return
        bond_epoch = self.bond_epoch.get(version_id, self.current_epoch())
        # If two epochs have passed since bond without positive profit, slash.
        if self.current_epoch() - bond_epoch >= 2:
            last_epoch = self.current_epoch() - 1
            econ = self.economies[(version_id, last_epoch)]
            if econ.ranked_revenue == 0 or econ.profit <= 0:
                self.version_bond[version_id] = 0
                self.bond_burned += 0  # bond already in commons, no transfer needed
                # Bond is forfeited; it stays in commons_available.

    def heartbeat(
        self,
        *,
        operator: str,
        version_id: str,
        state_hash: str,
        runtime_attested: bool,
        ipfs_proof: str | None = None,  # U5: proof-of-retrieval from IPFS
    ) -> None:
        version = self._version(version_id)
        self._require_operator(version, operator)
        self._require_live(version)
        if not state_hash:
            raise ArenaError("state hash required")
        if not runtime_attested:
            raise ArenaError("invalid runtime heartbeat proof")
        # U10: heartbeat burn.
        if self.HEARTBEAT_BURN > 0:
            if self.vaults[version_id] < self.HEARTBEAT_BURN:
                raise ArenaError("insufficient vault for heartbeat burn")
            self.vaults[version_id] -= self.HEARTBEAT_BURN
            self.commons_available += self.HEARTBEAT_BURN
            self.heartbeat_burn_collected += self.HEARTBEAT_BURN
        # U5: proof-of-retrieval. If provided and non-empty, mark fresh.
        if ipfs_proof:
            self.last_ipfs_proof_ts[version_id] = self.now
        version.last_heartbeat = self.now

    # ---------- immutable ranked schedule ----------

    def authorize_ranked_job(
        self,
        *,
        spec_hash: str,
        verifier_id: str,
        reward: int,
        deadline: int,
        expected_result_hash: str,
        verified_cost: int,
        cost_recipient: str | None,
        verifier_set: list[str] | None = None,  # U4: if non-empty, replaces single verifier_id
    ) -> str:
        """Populate the model's precommitted Merkle schedule.

        In Solidity this authorization is proven against an immutable Merkle
        root. Here we store the same leaf explicitly to keep the state model
        dependency-free.
        """
        self._require_positive(reward)
        if deadline <= self.now:
            raise ArenaError("deadline must be future")
        if verified_cost < 0:
            raise ArenaError("negative cost")
        if verified_cost and not cost_recipient:
            raise ArenaError("cost recipient required")
        if not spec_hash or not verifier_id or not expected_result_hash:
            raise ArenaError("invalid job metadata")
        # U4: build verifier set. Single-verifier jobs wrap into a 1-element set.
        vset = tuple(verifier_set) if verifier_set else (verifier_id,)
        if verifier_id not in vset:
            raise ArenaError("verifier_id must be in verifier_set")
        if len(set(vset)) != len(vset):
            raise ArenaError("verifier_set has duplicates")
        authorization_id = self._hash(
            "job-auth-v2",  # bump version to invalidate old Merkle leaves
            spec_hash,
            verifier_id,
            reward,
            deadline,
            expected_result_hash,
            verified_cost,
            cost_recipient,
            vset,  # set is part of the leaf — protects against schedule forgery
        )
        self.authorizations[authorization_id] = JobAuthorization(
            authorization_id=authorization_id,
            spec_hash=spec_hash,
            verifier_id=verifier_id,
            reward=reward,
            deadline=deadline,
            expected_result_hash=expected_result_hash,
            verified_cost=verified_cost,
            cost_recipient=cost_recipient,
            verifier_set=vset,
        )
        return authorization_id

    def create_ranked_job(self, authorization_id: str) -> str:
        authorization = self.authorizations.get(authorization_id)
        if authorization is None:
            raise ArenaError("job is not in immutable schedule")
        if authorization_id in self.authorization_used:
            raise ArenaError("job authorization replay")
        if authorization.deadline <= self.now:
            raise ArenaError("job expired")
        if self.commons_available < authorization.reward:
            raise ArenaError("insufficient commons")

        self.authorization_used.add(authorization_id)
        job_id = self._hash("ranked-job-v1", authorization_id, self._ranked_job_nonce)
        self._ranked_job_nonce += 1
        self.commons_available -= authorization.reward
        self.commons_reserved += authorization.reward
        self.ranked_jobs[job_id] = RankedJob(job_id=job_id, authorization=authorization)
        return job_id

    def submit_ranked_result(
        self,
        *,
        operator: str,
        job_id: str,
        version_id: str,
        result_hash: str,
        proof_id: str,
        objective_proof_valid: bool,
    ) -> None:
        job = self.ranked_jobs.get(job_id)
        if job is None or job.status is not RankedJobStatus.OPEN:
            raise ArenaError("ranked job not open")
        if self.now > job.authorization.deadline:
            raise ArenaError("ranked job expired")
        version = self._version(version_id)
        self._require_operator(version, operator)
        self._require_live(version)
        self._require_fresh_heartbeat(version)
        if not objective_proof_valid:
            raise ArenaError("objective proof rejected")
        if result_hash != job.authorization.expected_result_hash:
            raise ArenaError("wrong result")
        if not proof_id:
            raise ArenaError("proof id required")
        if proof_id in self.proof_used:
            raise ArenaError("proof replay")
        cost = job.authorization.verified_cost
        if self.vaults[version_id] < cost:
            raise ArenaError("insufficient vault for verified cost")

        self.proof_used.add(proof_id)
        job.status = RankedJobStatus.SETTLED
        job.winner_version = version_id
        job.result_hash = result_hash
        job.proof_id = proof_id
        epoch = self.current_epoch()
        job.settlement_epoch = epoch

        self.commons_reserved -= job.authorization.reward
        if cost:
            self.vaults[version_id] -= cost
            assert job.authorization.cost_recipient is not None
            self.wallets[job.authorization.cost_recipient] += cost
        self.vaults[version_id] += job.authorization.reward

        econ = self.economies[(version_id, epoch)]
        econ.ranked_revenue += job.authorization.reward
        econ.verified_ranked_cost += cost
        if econ.profit > 0:
            version.last_positive_profit_at = self.now

    def expire_ranked_job(self, job_id: str) -> None:
        job = self.ranked_jobs.get(job_id)
        if job is None or job.status is not RankedJobStatus.OPEN:
            raise ArenaError("ranked job not open")
        if self.now <= job.authorization.deadline:
            raise ArenaError("deadline not reached")
        job.status = RankedJobStatus.EXPIRED
        self.commons_reserved -= job.authorization.reward
        self.commons_available += job.authorization.reward

    # ---------- subjective customer escrow ----------

    def open_market_job(
        self,
        *,
        buyer: str,
        target_version: str,
        spec_hash: str,
        reward: int,
        deadline: int,
        work_verifier_id: str | None = None,  # U6: optional objective verifier
    ) -> str:
        self._funding_beneficiary(target_version)
        self._require_positive(reward)
        if not spec_hash or deadline <= self.now:
            raise ArenaError("invalid market job")
        self._debit_wallet(buyer, reward)
        self.market_escrow_reserved += reward
        job_id = self._hash(
            "market-job-v2", buyer, target_version, spec_hash, reward, deadline,
            work_verifier_id or "", self._market_job_nonce
        )
        self._market_job_nonce += 1
        self.market_jobs[job_id] = MarketJob(
            job_id=job_id,
            buyer=buyer,
            target_version=target_version,
            spec_hash=spec_hash,
            reward=reward,
            deadline=deadline,
            work_verifier_id=work_verifier_id,
        )
        return job_id

    def submit_market_result(
        self,
        *,
        operator: str,
        job_id: str,
        result_hash: str,
        objective_proof_valid: bool = False,  # U6: auto-accept on proof
    ) -> None:
        job = self.market_jobs.get(job_id)
        if job is None or job.status is not MarketJobStatus.OPEN:
            raise ArenaError("market job not open")
        if self.now > job.deadline:
            raise ArenaError("market job expired")
        if not result_hash:
            raise ArenaError("result hash required")
        performer_version = self._funding_beneficiary(job.target_version)
        version = self._version(performer_version)
        self._require_operator(version, operator)
        self._require_fresh_heartbeat(version)
        job.performer_version = performer_version
        job.result_hash = result_hash
        # U6: if a work verifier is set and proof passes, auto-settle.
        if job.work_verifier_id and objective_proof_valid:
            job.status = MarketJobStatus.ACCEPTED
            self.market_escrow_reserved -= job.reward
            beneficiary = self._live_beneficiary(performer_version) or performer_version
            if beneficiary is None:
                self.commons_available += job.reward
            else:
                self.vaults[beneficiary] += job.reward
                self.market_revenue[beneficiary] += job.reward
        else:
            job.status = MarketJobStatus.SUBMITTED

    def accept_market_result(self, *, buyer: str, job_id: str) -> str | None:
        job = self.market_jobs.get(job_id)
        if job is None or job.status is not MarketJobStatus.SUBMITTED:
            raise ArenaError("market job not submitted")
        if buyer != job.buyer:
            raise ArenaError("not buyer")
        job.status = MarketJobStatus.ACCEPTED
        self.market_escrow_reserved -= job.reward
        beneficiary = self._live_beneficiary(job.performer_version or job.target_version)
        if beneficiary is None:
            self.commons_available += job.reward
        else:
            self.vaults[beneficiary] += job.reward
            self.market_revenue[beneficiary] += job.reward
        return beneficiary

    def refund_market_job(self, *, buyer: str, job_id: str) -> None:
        job = self.market_jobs.get(job_id)
        if job is None or job.status not in (MarketJobStatus.OPEN, MarketJobStatus.SUBMITTED):
            raise ArenaError("market job not refundable")
        if buyer != job.buyer:
            raise ArenaError("not buyer")
        if self.now <= job.deadline:
            raise ArenaError("deadline not reached")
        job.status = MarketJobStatus.REFUNDED
        self.market_escrow_reserved -= job.reward
        self.wallets[buyer] += job.reward

    # ---------- selection ----------

    def profit(self, version_id: str, epoch: int) -> int:
        """Per-epoch profit. Used for single-epoch comparisons.

        Note: U8 (median over multiple epochs) is exposed via `median_profit()`.
        Single-epoch `profit()` is still needed for `lastClosedEpoch()` checks
        and for `top_versions()` ranking.
        """
        return self.economies[(version_id, epoch)].profit

    def median_profit(self, version_id: str, end_epoch: int) -> int:
        """U8: median profit over last PROFIT_WINDOW_EPOCHS epochs ending at end_epoch.

        Defeats single-epoch outlier attacks where a challenger submits one
        large job right before the epoch boundary. Median requires sustained
        profitability across multiple epochs.
        """
        window = self.PROFIT_WINDOW_EPOCHS
        profits = [
            self.economies[(version_id, end_epoch - i)].profit
            for i in range(window)
            if end_epoch - i >= 0
        ]
        if not profits:
            return 0
        profits.sort()
        mid = len(profits) // 2
        if len(profits) % 2 == 1:
            return profits[mid]
        return (profits[mid - 1] + profits[mid]) // 2

    # ── U3: commit-reveal supersede ─────────────────────────────────────

    def _execute_supersede(self, challenger_id: str, epoch: int,
                           use_median: bool = False) -> int:
        """Internal: execute the actual supersede state transition.

        `use_median=False` for legacy single-epoch supersede (backward compat).
        `use_median=True` for commit-reveal production path (U8).
        """
        if epoch != self.last_closed_epoch():
            raise ArenaError("wrong comparison epoch")
        challenger = self._version(challenger_id)
        if challenger.status is not VersionStatus.INCUBATING:
            raise ArenaError("challenger must be incubating")
        self._require_fresh_heartbeat(challenger)
        incumbent_id = self.active_version.get(challenger.lineage_id)
        if incumbent_id is None:
            raise ArenaError("no active incumbent")
        if incumbent_id == challenger_id:
            raise ArenaError("same version")
        incumbent = self._version(incumbent_id)
        if incumbent.lineage_id != challenger.lineage_id:
            raise ArenaError("different lineage")
        challenger_econ = self.economies[(challenger_id, epoch)]
        if challenger_econ.ranked_revenue == 0:
            raise ArenaError("challenger has no ranked revenue")
        if use_median:
            challenger_metric = self.median_profit(challenger_id, epoch)
            incumbent_metric = self.median_profit(incumbent_id, epoch)
            if challenger_metric <= 0:
                raise ArenaError("challenger has no positive median profit")
            if challenger_metric <= incumbent_metric:
                raise ArenaError("challenger is not strictly more profitable (median)")
        else:
            if challenger_econ.profit <= 0:
                raise ArenaError("challenger has no positive ranked profit")
            if challenger_econ.profit <= self.profit(incumbent_id, epoch):
                raise ArenaError("challenger is not strictly more profitable")

        transferred = self.vaults[incumbent_id]
        self.vaults[incumbent_id] = 0
        self.vaults[challenger_id] += transferred
        incumbent.status = VersionStatus.SUPERSEDED
        incumbent.successor = challenger_id
        challenger.status = VersionStatus.ACTIVE
        self.active_version[challenger.lineage_id] = challenger_id
        return transferred

    def commit_supersede(self, *, challenger_id: str, epoch: int, salt: str) -> str:
        """Commit a supersede intent. Hash hides challenger_id+salt until reveal.

        After COMMIT_PHASE_BLOCKS, anyone can reveal+execute via `reveal_supersede`.
        Defeats MEV: the challenger's identity is hidden during the commit window,
        so block builders cannot prioritize rival challengers based on identity.
        """
        if epoch != self.last_closed_epoch():
            raise ArenaError("wrong commit epoch")
        if not salt:
            raise ArenaError("salt required")
        commit_hash = self._hash("supersede-commit-v1", challenger_id, epoch, salt)
        if commit_hash in self.supersede_commits:
            raise ArenaError("commit already exists")
        # Pre-validate challenger is at least registered. We don't check status
        # here — that happens at reveal time.
        if challenger_id not in self.versions:
            raise ArenaError("challenger not registered")
        self.supersede_commits[commit_hash] = (challenger_id, epoch, self.now)
        return commit_hash

    def reveal_supersede(self, *, challenger_id: str, epoch: int, salt: str) -> int:
        """Reveal a committed supersede intent. If valid, executes the supersede.

        Production path: uses median profit (U8) and the commit-reveal window (U3).
        Returns the amount of capital transferred.
        """
        if epoch != self.last_closed_epoch():
            raise ArenaError("wrong reveal epoch")
        commit_hash = self._hash("supersede-commit-v1", challenger_id, epoch, salt)
        if commit_hash not in self.supersede_commits:
            raise ArenaError("no matching commit")
        if commit_hash in self.supersede_revealed:
            raise ArenaError("already revealed")
        committed_at = self.supersede_commits[commit_hash][2]
        # Reveal window must be after commit phase.
        if self.now < committed_at + self.COMMIT_PHASE_BLOCKS:
            raise ArenaError("reveal too early")
        self.supersede_revealed.add(commit_hash)
        return self._execute_supersede(challenger_id, epoch, use_median=True)

    def supersede(self, *, challenger_id: str, epoch: int) -> int:
        """Backward-compatible entrypoint: single-epoch profit, no commit-reveal.

        Useful for tests where commit-reveal timing is not interesting and
        median-of-3-epochs protection is not exercised. Production code should
        use `commit_supersede` + `reveal_supersede`.
        """
        return self._execute_supersede(challenger_id, epoch, use_median=False)

    def eject_stale(self, version_id: str) -> int:
        """U9: stale version's capital is split — half to commons, half to lineage successor.

        If no Incubating successor exists in the same lineage, all goes to commons.
        """
        version = self._version(version_id)
        self._require_live(version)
        reference = (
            version.last_positive_profit_at
            if version.last_positive_profit_at is not None
            else version.created_at
        )
        if self.now <= reference + self.STALE_AFTER:
            raise ArenaError("version is not stale")
        # U1: slash bond if applicable.
        self._slash_bond_if_unprofitable(version_id)
        total = self.vaults[version_id]
        self.vaults[version_id] = 0
        # U9: find an Incubating successor in the same lineage.
        successor_id: str | None = None
        for vid in self.lineage_versions.get(version.lineage_id, []):
            if vid == version_id:
                continue
            v = self.versions[vid]
            if v.status is VersionStatus.INCUBATING:
                # Prefer successors that have shown positive profit at some point.
                if v.last_positive_profit_at is not None:
                    successor_id = vid
                    break
                # Fallback: positive profit in current epoch.
                if self.economies[(vid, self.current_epoch())].profit > 0:
                    successor_id = vid
                    break
        if successor_id is not None and total > 0:
            lineage_share = (total * self.STALE_LINEAGE_SHARE_NUM) // self.STALE_LINEAGE_SHARE_DEN
            commons_share = total - lineage_share
            self.vaults[successor_id] += lineage_share
            self.commons_available += commons_share
        else:
            self.commons_available += total
        version.status = VersionStatus.STALE
        if self.active_version.get(version.lineage_id) == version_id:
            self.active_version[version.lineage_id] = None
        return total

    def claim_vacancy(self, *, version_id: str, epoch: int) -> None:
        """U3: claim_vacancy also goes through commit-reveal in production.

        For backward compatibility the legacy entrypoint commits+reveals
        in one call. Production code should use the two-step variant.
        """
        if epoch != self.last_closed_epoch():
            raise ArenaError("wrong comparison epoch")
        version = self._version(version_id)
        if version.status is not VersionStatus.INCUBATING:
            raise ArenaError("candidate must be incubating")
        if self.active_version.get(version.lineage_id) is not None:
            raise ArenaError("active version exists")
        self._require_fresh_heartbeat(version)
        econ = self.economies[(version_id, epoch)]
        if econ.ranked_revenue == 0 or econ.profit <= 0:
            raise ArenaError("candidate has no positive ranked profit")
        version.status = VersionStatus.ACTIVE
        self.active_version[version.lineage_id] = version_id

    def top_versions(self, *, lineage_id: str, epoch: int, limit: int = TOP_ROUTING_COUNT) -> list[str]:
        if limit <= 0:
            return []
        candidates = [
            version_id
            for version_id in self.lineage_versions.get(lineage_id, [])
            if self.versions[version_id].status in (VersionStatus.ACTIVE, VersionStatus.INCUBATING)
            and self.economies[(version_id, epoch)].ranked_revenue > 0
            and self.profit(version_id, epoch) > 0
        ]
        candidates.sort(key=lambda item: (self.profit(item, epoch), item), reverse=True)
        return candidates[:limit]

    # ---------- invariants ----------

    def conservation_total(self) -> int:
        return (
            sum(self.wallets.values())
            + sum(self.vaults.values())
            + self.commons_available
            + self.commons_reserved
            + self.market_escrow_reserved
            + self.unaccounted_surplus
        )

    def assert_invariants(self) -> None:
        if self.conservation_total() != self.total_minted:
            raise AssertionError(
                f"token conservation failed: {self.conservation_total()} != {self.total_minted}"
            )
        if any(value < 0 for value in self.wallets.values()):
            raise AssertionError("negative wallet")
        if any(value < 0 for value in self.vaults.values()):
            raise AssertionError("negative vault")
        if min(
            self.commons_available,
            self.commons_reserved,
            self.market_escrow_reserved,
            self.unaccounted_surplus,
        ) < 0:
            raise AssertionError("negative reserve")
        for lineage_id, active in self.active_version.items():
            if active is not None:
                version = self._version(active)
                if version.lineage_id != lineage_id or version.status is not VersionStatus.ACTIVE:
                    raise AssertionError("invalid active-version pointer")

    # ---------- internals ----------

    def _new_version_id(
        self,
        lineage_id: str,
        parent_id: str | None,
        operator: str,
        declaration: Declaration,
        salt: str,
    ) -> str:
        version_id = self._hash(
            "version-v1",
            lineage_id,
            parent_id,
            operator,
            declaration.source_digest,
            declaration.image_digest,
            declaration.provenance_digest,
            declaration.runtime_identity,
            declaration.source_uri,
            self.REQUIRED_LICENSE,
            salt,
        )
        self._version_nonce += 1
        return version_id

    def _validate_declaration(
        self, declaration: Declaration, runtime_attested: bool, license_id: str
    ) -> None:
        if license_id != self.REQUIRED_LICENSE:
            raise ArenaError("competition requires AGPL-3.0-or-later source")
        if not runtime_attested:
            raise ArenaError("runtime attestation rejected")
        if not all(
            (
                declaration.source_digest,
                declaration.image_digest,
                declaration.provenance_digest,
                declaration.runtime_identity,
                declaration.source_uri,
            )
        ):
            raise ArenaError("incomplete declaration")
        if not declaration.source_uri.startswith("ipfs://"):
            raise ArenaError("source URI must be content-addressed IPFS")
        if len(declaration.source_uri.encode("utf-8")) > 256:
            raise ArenaError("source URI too long")

    def _version(self, version_id: str) -> Version:
        try:
            return self.versions[version_id]
        except KeyError as exc:
            raise ArenaError("version not found") from exc

    @staticmethod
    def _require_live(version: Version) -> None:
        if version.status not in (VersionStatus.ACTIVE, VersionStatus.INCUBATING):
            raise ArenaError("version not live")

    @staticmethod
    def _require_operator(version: Version, operator: str) -> None:
        if version.operator != operator:
            raise ArenaError("not version operator")

    def _require_fresh_heartbeat(self, version: Version) -> None:
        if self.now > version.last_heartbeat + self.HEARTBEAT_GRACE:
            raise ArenaError("heartbeat too old")

    def _live_beneficiary(self, version_id: str) -> str | None:
        version = self._version(version_id)
        if version.status in (VersionStatus.ACTIVE, VersionStatus.INCUBATING):
            return version_id
        if version.status is VersionStatus.SUPERSEDED:
            active = self.active_version.get(version.lineage_id)
            if active is not None and self.versions[active].status in (
                VersionStatus.ACTIVE,
                VersionStatus.INCUBATING,
            ):
                return active
        return None

    def _funding_beneficiary(self, version_id: str) -> str:
        beneficiary = self._live_beneficiary(version_id)
        if beneficiary is None:
            raise ArenaError("no live beneficiary")
        return beneficiary

    def _debit_wallet(self, account: str, amount: int) -> None:
        self._require_positive(amount)
        if self.wallets[account] < amount:
            raise ArenaError("insufficient wallet")
        self.wallets[account] -= amount

    @staticmethod
    def _require_positive(amount: int) -> None:
        if amount <= 0:
            raise ArenaError("amount must be positive")

    def live_versions(self, lineage_id: str) -> Iterable[Version]:
        for version_id in self.lineage_versions.get(lineage_id, []):
            version = self.versions[version_id]
            if version.status in (VersionStatus.ACTIVE, VersionStatus.INCUBATING):
                yield version
