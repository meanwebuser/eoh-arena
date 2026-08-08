"""Deterministic reference model for EOH Arena.

This model is intentionally stricter than a normal SaaS ledger:

* donations and subjective market payments never affect rank;
* only pre-authorized objective jobs create ranked revenue;
* ranked result, verified cost, provider payment and reward settle atomically;
* protocol-held capital has no arbitrary withdrawal path;
* a strictly more profitable child can supersede the incumbent without consent;
* stale versions are economically ejected into the commons.

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


class Arena:
    """Pure-Python state machine with token conservation checks."""

    EPOCH_LENGTH = 7 * 24 * 60 * 60
    STALE_AFTER = 30 * 24 * 60 * 60
    HEARTBEAT_PERIOD = 60 * 60
    HEARTBEAT_GRACE = 2 * 60 * 60
    TOP_ROUTING_COUNT = 3
    REQUIRED_LICENSE = "AGPL-3.0-or-later"

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

        self.commons_available = 0
        self.commons_reserved = 0
        self.market_escrow_reserved = 0
        self.unaccounted_surplus = 0

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

        self.proof_used.add(proof_id)
        self.vaults[version_id] -= amount
        self.operating_spent[version_id] += amount
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
    ) -> tuple[str, str]:
        self._validate_declaration(declaration, runtime_attested, license_id)
        lineage_id = self._hash("lineage-v1", operator, declaration.source_digest, salt)
        if lineage_id in self.active_version:
            raise ArenaError("lineage already exists")
        version_id = self._new_version_id(lineage_id, None, operator, declaration, salt)
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
        )
        self.lineage_versions[lineage_id].append(version_id)
        return version_id

    def heartbeat(
        self,
        *,
        operator: str,
        version_id: str,
        state_hash: str,
        runtime_attested: bool,
    ) -> None:
        version = self._version(version_id)
        self._require_operator(version, operator)
        self._require_live(version)
        if not state_hash:
            raise ArenaError("state hash required")
        if not runtime_attested:
            raise ArenaError("invalid runtime heartbeat proof")
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
        authorization_id = self._hash(
            "job-auth-v1",
            spec_hash,
            verifier_id,
            reward,
            deadline,
            expected_result_hash,
            verified_cost,
            cost_recipient,
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
    ) -> str:
        self._funding_beneficiary(target_version)
        self._require_positive(reward)
        if not spec_hash or deadline <= self.now:
            raise ArenaError("invalid market job")
        self._debit_wallet(buyer, reward)
        self.market_escrow_reserved += reward
        job_id = self._hash(
            "market-job-v1", buyer, target_version, spec_hash, reward, deadline, self._market_job_nonce
        )
        self._market_job_nonce += 1
        self.market_jobs[job_id] = MarketJob(
            job_id=job_id,
            buyer=buyer,
            target_version=target_version,
            spec_hash=spec_hash,
            reward=reward,
            deadline=deadline,
        )
        return job_id

    def submit_market_result(
        self, *, operator: str, job_id: str, result_hash: str
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
        return self.economies[(version_id, epoch)].profit

    def supersede(self, *, challenger_id: str, epoch: int) -> int:
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

    def eject_stale(self, version_id: str) -> int:
        version = self._version(version_id)
        self._require_live(version)
        reference = (
            version.last_positive_profit_at
            if version.last_positive_profit_at is not None
            else version.created_at
        )
        if self.now <= reference + self.STALE_AFTER:
            raise ArenaError("version is not stale")
        moved = self.vaults[version_id]
        self.vaults[version_id] = 0
        self.commons_available += moved
        version.status = VersionStatus.STALE
        if self.active_version.get(version.lineage_id) == version_id:
            self.active_version[version.lineage_id] = None
        return moved

    def claim_vacancy(self, *, version_id: str, epoch: int) -> None:
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
