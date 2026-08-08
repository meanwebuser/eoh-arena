// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

import {IERC20Minimal} from "./interfaces/IERC20Minimal.sol";
import {IRuntimeVerifier} from "./interfaces/IRuntimeVerifier.sol";
import {IWorkVerifier} from "./interfaces/IWorkVerifier.sol";
import {IExpenseVerifier} from "./interfaces/IExpenseVerifier.sol";
import {IJobAuthorizer} from "./interfaces/IJobAuthorizer.sol";
import {SafeTransfer} from "./libraries/SafeTransfer.sol";

/// @title EOH Arena
/// @notice Non-upgradeable reference protocol in which open-source agent
/// versions compete for protocol-held capital using objectively verified work.
/// @dev There is deliberately no owner, admin halt, arbitrary vault withdrawal,
/// or ranking contribution from donations and subjective customer payments.
contract EohArena {
    using SafeTransfer for IERC20Minimal;

    uint64 public constant EPOCH_LENGTH = 7 days;
    uint64 public constant STALE_AFTER = 30 days;
    uint64 public constant HEARTBEAT_PERIOD = 1 hours;
    uint64 public constant HEARTBEAT_GRACE = 2 hours;
    uint16 public constant TOP_ROUTING_COUNT = 3;

    bytes32 public constant REQUIRED_LICENSE_HASH = keccak256("AGPL-3.0-or-later");
    bytes32 public constant VERSION_DOMAIN = keccak256("EOH_VERSION_V1");
    uint256 public constant MAX_SOURCE_URI_BYTES = 256;

    IERC20Minimal public immutable settlementToken;
    IRuntimeVerifier public immutable runtimeVerifier;
    IExpenseVerifier public immutable expenseVerifier;
    IJobAuthorizer public immutable rankedJobAuthorizer;

    enum VersionStatus {
        None,
        Incubating,
        Active,
        Superseded,
        Stale
    }

    enum RankedJobStatus {
        None,
        Open,
        Settled,
        Expired
    }

    enum MarketJobStatus {
        None,
        Open,
        Submitted,
        Accepted,
        Refunded
    }

    struct VersionDeclaration {
        bytes32 licenseHash;
        bytes32 sourceDigest;
        bytes32 imageDigest;
        bytes32 provenanceDigest;
        bytes32 runtimeIdentity;
        string sourceURI;
    }

    struct Version {
        bytes32 lineageId;
        bytes32 parentId;
        address operator;
        bytes32 licenseHash;
        bytes32 sourceDigest;
        bytes32 imageDigest;
        bytes32 provenanceDigest;
        bytes32 runtimeIdentity;
        uint64 createdAt;
        uint64 lastHeartbeat;
        uint64 lastPositiveProfitAt;
        VersionStatus status;
        bytes32 successor;
        string sourceURI;
    }

    struct Economy {
        uint128 rankedRevenue;
        uint128 verifiedRankedCost;
    }

    struct RankedJob {
        bytes32 specHash;
        address verifier;
        uint128 reward;
        uint64 deadline;
        uint64 settlementEpoch;
        RankedJobStatus status;
        bytes32 winnerVersion;
        bytes32 resultHash;
        bytes32 proofId;
    }

    struct MarketJob {
        address buyer;
        bytes32 targetVersion;
        bytes32 specHash;
        bytes32 resultHash;
        bytes32 performerVersion;
        uint128 reward;
        uint64 deadline;
        MarketJobStatus status;
    }

    mapping(bytes32 versionId => Version) private _versions;
    mapping(bytes32 lineageId => bytes32 activeVersionId) public activeVersion;
    mapping(bytes32 lineageId => bytes32[]) private _lineageVersions;
    mapping(bytes32 lineageId => bool) public lineageExists;

    mapping(bytes32 versionId => uint256) public vaultBalance;
    mapping(bytes32 versionId => uint256) public capitalIn;
    mapping(bytes32 versionId => uint256) public marketRevenue;
    mapping(bytes32 versionId => uint256) public operatingSpent;
    mapping(bytes32 versionId => mapping(uint64 epoch => Economy)) private _economy;

    uint256 public commonsAvailable;
    uint256 public commonsReserved;
    uint256 public marketEscrowReserved;
    uint256 public totalVaultBalance;

    mapping(bytes32 jobId => RankedJob) public rankedJobs;
    mapping(bytes32 jobId => MarketJob) public marketJobs;
    mapping(bytes32 proofId => bool) public proofUsed;
    mapping(bytes32 authorizationId => bool) public jobAuthorizationUsed;

    uint256 private _rankedJobNonce;
    uint256 private _marketJobNonce;
    uint256 private _reentrancyLock = 1;

    error ZeroAddress();
    error ZeroAmount();
    error InvalidMetadata();
    error InvalidRuntimeProof();
    error VersionAlreadyExists();
    error VersionNotFound();
    error LineageAlreadyExists();
    error LineageNotFound();
    error ParentMismatch();
    error NotOperator();
    error NotLive();
    error InvalidJobAuthorization();
    error JobAuthorizationAlreadyUsed();
    error JobNotOpen();
    error JobNotSubmitted();
    error JobExpired();
    error DeadlineNotReached();
    error InsufficientCommons();
    error InsufficientVault();
    error InvalidWorkProof();
    error InvalidExpenseProof();
    error ProofAlreadyUsed();
    error HeartbeatTooOld();
    error WrongEpoch();
    error NoActiveVersion();
    error ActiveVersionExists();
    error SameVersion();
    error DifferentLineage();
    error ChallengerHasNoRankedRevenue();
    error NotMoreProfitable();
    error NotStale();
    error NoPositiveProfit();
    error NotBuyer();
    error Reentrancy();

    event LineageCreated(bytes32 indexed lineageId, bytes32 indexed rootVersionId);
    event VersionRegistered(
        bytes32 indexed versionId,
        bytes32 indexed lineageId,
        bytes32 indexed parentId,
        address operator,
        bytes32 licenseHash,
        bytes32 sourceDigest,
        bytes32 imageDigest,
        bytes32 provenanceDigest,
        bytes32 runtimeIdentity,
        string sourceURI
    );
    event Heartbeat(bytes32 indexed versionId, bytes32 indexed stateHash, uint64 timestamp);
    event Donation(bytes32 indexed versionId, address indexed donor, uint256 amount);
    event CommonsFunded(address indexed donor, uint256 amount);
    event OperatingExpense(
        bytes32 indexed versionId,
        bytes32 indexed expenseId,
        address indexed recipient,
        uint128 amount,
        bytes32 payloadHash,
        bytes32 proofId
    );
    event RankedJobCreated(
        bytes32 indexed jobId,
        bytes32 indexed specHash,
        address indexed verifier,
        uint128 reward,
        uint64 deadline
    );
    event RankedJobSettled(
        bytes32 indexed jobId,
        bytes32 indexed versionId,
        bytes32 indexed resultHash,
        uint128 reward,
        uint128 verifiedCost,
        address costRecipient,
        bytes32 proofId,
        uint64 epoch
    );
    event RankedJobExpired(bytes32 indexed jobId, uint128 rewardReturned);
    event MarketJobOpened(
        bytes32 indexed jobId,
        address indexed buyer,
        bytes32 indexed targetVersion,
        uint128 reward,
        uint64 deadline,
        bytes32 specHash
    );
    event MarketResultSubmitted(
        bytes32 indexed jobId,
        bytes32 indexed performerVersion,
        bytes32 indexed resultHash
    );
    event MarketJobAccepted(bytes32 indexed jobId, bytes32 indexed beneficiary, uint128 reward);
    event MarketJobRefunded(bytes32 indexed jobId, uint128 reward);
    event Superseded(
        bytes32 indexed lineageId,
        bytes32 indexed incumbentVersion,
        bytes32 indexed challengerVersion,
        uint64 epoch,
        int256 incumbentProfit,
        int256 challengerProfit,
        uint256 capitalTransferred
    );
    event VersionStaled(bytes32 indexed versionId, uint256 movedToCommons);
    event VacancyClaimed(bytes32 indexed lineageId, bytes32 indexed versionId, uint64 epoch);
    event SurplusAbsorbed(address indexed caller, uint256 amount);

    modifier nonReentrant() {
        if (_reentrancyLock != 1) revert Reentrancy();
        _reentrancyLock = 2;
        _;
        _reentrancyLock = 1;
    }

    constructor(
        IERC20Minimal settlementToken_,
        IRuntimeVerifier runtimeVerifier_,
        IExpenseVerifier expenseVerifier_,
        IJobAuthorizer rankedJobAuthorizer_
    ) {
        if (
            address(settlementToken_) == address(0) ||
            address(runtimeVerifier_) == address(0) ||
            address(expenseVerifier_) == address(0) ||
            address(rankedJobAuthorizer_) == address(0)
        ) revert ZeroAddress();
        if (
            address(settlementToken_).code.length == 0 ||
            address(runtimeVerifier_).code.length == 0 ||
            address(expenseVerifier_).code.length == 0 ||
            address(rankedJobAuthorizer_).code.length == 0
        ) revert ZeroAddress();

        settlementToken = settlementToken_;
        runtimeVerifier = runtimeVerifier_;
        expenseVerifier = expenseVerifier_;
        rankedJobAuthorizer = rankedJobAuthorizer_;
    }

    function createLineage(
        VersionDeclaration calldata declaration,
        bytes calldata runtimeProof,
        bytes32 salt
    ) external returns (bytes32 lineageId, bytes32 versionId) {
        _validateDeclaration(declaration);

        lineageId = keccak256(
            abi.encode(
                "EOH_LINEAGE_V1",
                block.chainid,
                address(this),
                msg.sender,
                declaration.sourceDigest,
                salt
            )
        );
        if (lineageExists[lineageId]) revert LineageAlreadyExists();

        versionId = computeVersionId(lineageId, bytes32(0), msg.sender, declaration, salt);
        if (_versions[versionId].status != VersionStatus.None) revert VersionAlreadyExists();
        _verifyRuntime(msg.sender, declaration, runtimeProof);

        lineageExists[lineageId] = true;
        _storeVersion(versionId, lineageId, bytes32(0), msg.sender, declaration, VersionStatus.Active);
        activeVersion[lineageId] = versionId;

        emit LineageCreated(lineageId, versionId);
    }

    function registerVersion(
        bytes32 lineageId,
        bytes32 parentId,
        VersionDeclaration calldata declaration,
        bytes calldata runtimeProof,
        bytes32 salt
    ) external returns (bytes32 versionId) {
        if (!lineageExists[lineageId]) revert LineageNotFound();
        Version storage parent = _versions[parentId];
        if (parent.status == VersionStatus.None) revert VersionNotFound();
        if (parent.lineageId != lineageId) revert ParentMismatch();
        _validateDeclaration(declaration);

        versionId = computeVersionId(lineageId, parentId, msg.sender, declaration, salt);
        if (_versions[versionId].status != VersionStatus.None) revert VersionAlreadyExists();
        _verifyRuntime(msg.sender, declaration, runtimeProof);

        _storeVersion(versionId, lineageId, parentId, msg.sender, declaration, VersionStatus.Incubating);
    }

    function computeVersionId(
        bytes32 lineageId,
        bytes32 parentId,
        address operator,
        VersionDeclaration calldata declaration,
        bytes32 salt
    ) public pure returns (bytes32) {
        return keccak256(
            abi.encode(
                VERSION_DOMAIN,
                lineageId,
                parentId,
                operator,
                declaration.licenseHash,
                declaration.sourceDigest,
                declaration.imageDigest,
                declaration.provenanceDigest,
                declaration.runtimeIdentity,
                keccak256(bytes(declaration.sourceURI)),
                salt
            )
        );
    }

    function heartbeat(
        bytes32 versionId,
        bytes32 stateHash,
        bytes calldata runtimeProof
    ) external {
        Version storage version = _requireVersion(versionId);
        if (msg.sender != version.operator) revert NotOperator();
        if (!_isLive(version.status)) revert NotLive();
        if (stateHash == bytes32(0)) revert InvalidMetadata();

        uint64 observedAt = uint64(block.timestamp);
        bool valid = runtimeVerifier.verifyHeartbeat(
            versionId,
            version.runtimeIdentity,
            stateHash,
            observedAt,
            runtimeProof
        );
        if (!valid) revert InvalidRuntimeProof();

        version.lastHeartbeat = observedAt;
        emit Heartbeat(versionId, stateHash, observedAt);
    }

    /// @notice Capital supports survival but never contributes to rank.
    function donate(bytes32 versionId, uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        bytes32 beneficiary = _fundingBeneficiary(versionId);

        settlementToken.safeTransferFrom(msg.sender, address(this), amount);
        vaultBalance[beneficiary] += amount;
        totalVaultBalance += amount;
        capitalIn[beneficiary] += amount;

        emit Donation(beneficiary, msg.sender, amount);
    }

    function fundCommons(uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        settlementToken.safeTransferFrom(msg.sender, address(this), amount);
        commonsAvailable += amount;
        emit CommonsFunded(msg.sender, amount);
    }

    /// @notice The only generic way for protocol-held agent capital to leave a
    /// vault. The immutable expense verifier must validate the provider receipt.
    /// This expense does not affect competition rank unless a ranked-work
    /// verifier also binds it to a ranked result.
    function settleOperatingExpense(
        bytes32 versionId,
        bytes32 expenseId,
        address recipient,
        uint128 amount,
        bytes32 payloadHash,
        bytes calldata proof
    ) external nonReentrant {
        Version storage version = _requireVersion(versionId);
        if (msg.sender != version.operator) revert NotOperator();
        if (!_isLive(version.status)) revert NotLive();
        if (recipient == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        if (vaultBalance[versionId] < amount) revert InsufficientVault();

        (bool valid, bytes32 proofId) = expenseVerifier.verifyExpense(
            versionId,
            expenseId,
            recipient,
            amount,
            payloadHash,
            proof
        );
        if (!valid || proofId == bytes32(0)) revert InvalidExpenseProof();
        if (proofUsed[proofId]) revert ProofAlreadyUsed();

        proofUsed[proofId] = true;
        vaultBalance[versionId] -= amount;
        totalVaultBalance -= amount;
        operatingSpent[versionId] += amount;
        settlementToken.safeTransfer(recipient, amount);

        emit OperatingExpense(
            versionId,
            expenseId,
            recipient,
            amount,
            payloadHash,
            proofId
        );
    }

    function createRankedJob(
        bytes32 specHash,
        address verifier,
        uint128 reward,
        uint64 deadline,
        bytes calldata authorizationProof
    ) external returns (bytes32 jobId) {
        if (specHash == bytes32(0) || verifier == address(0) || verifier.code.length == 0) {
            revert InvalidMetadata();
        }
        if (reward == 0) revert ZeroAmount();
        if (deadline <= block.timestamp) revert JobExpired();
        if (commonsAvailable < reward) revert InsufficientCommons();

        (bool authorized, bytes32 authorizationId) = rankedJobAuthorizer.authorizeJob(
            specHash,
            verifier,
            reward,
            deadline,
            authorizationProof
        );
        if (!authorized || authorizationId == bytes32(0)) revert InvalidJobAuthorization();
        if (jobAuthorizationUsed[authorizationId]) revert JobAuthorizationAlreadyUsed();
        jobAuthorizationUsed[authorizationId] = true;

        jobId = keccak256(
            abi.encode(
                "EOH_RANKED_JOB_V1",
                address(this),
                block.chainid,
                specHash,
                verifier,
                reward,
                deadline,
                authorizationId,
                _rankedJobNonce++
            )
        );

        commonsAvailable -= reward;
        commonsReserved += reward;
        rankedJobs[jobId] = RankedJob({
            specHash: specHash,
            verifier: verifier,
            reward: reward,
            deadline: deadline,
            settlementEpoch: 0,
            status: RankedJobStatus.Open,
            winnerVersion: bytes32(0),
            resultHash: bytes32(0),
            proofId: bytes32(0)
        });

        emit RankedJobCreated(jobId, specHash, verifier, reward, deadline);
    }

    /// @notice Result, provider payment, reward, and rank accounting settle in
    /// one transaction. A participant cannot separately invent the ranked cost.
    function submitRankedResult(
        bytes32 jobId,
        bytes32 versionId,
        bytes32 resultHash,
        bytes calldata proof
    ) external nonReentrant {
        RankedJob storage job = rankedJobs[jobId];
        if (job.status != RankedJobStatus.Open) revert JobNotOpen();
        if (block.timestamp > job.deadline) revert JobExpired();

        Version storage version = _requireVersion(versionId);
        if (msg.sender != version.operator) revert NotOperator();
        if (!_isLive(version.status)) revert NotLive();
        _requireFreshHeartbeat(version);

        (
            bool valid,
            bytes32 proofId,
            uint128 verifiedCost,
            address costRecipient
        ) = IWorkVerifier(job.verifier).verify(
            jobId,
            versionId,
            job.specHash,
            resultHash,
            proof
        );

        if (!valid || proofId == bytes32(0)) revert InvalidWorkProof();
        if (proofUsed[proofId]) revert ProofAlreadyUsed();
        if (verifiedCost > 0 && costRecipient == address(0)) revert InvalidWorkProof();
        if (vaultBalance[versionId] < verifiedCost) revert InsufficientVault();

        uint64 epoch = currentEpoch();
        proofUsed[proofId] = true;
        job.status = RankedJobStatus.Settled;
        job.settlementEpoch = epoch;
        job.winnerVersion = versionId;
        job.resultHash = resultHash;
        job.proofId = proofId;

        commonsReserved -= job.reward;
        if (verifiedCost > 0) {
            vaultBalance[versionId] -= verifiedCost;
            totalVaultBalance -= verifiedCost;
            settlementToken.safeTransfer(costRecipient, verifiedCost);
        }
        vaultBalance[versionId] += job.reward;
        totalVaultBalance += job.reward;

        Economy storage econ = _economy[versionId][epoch];
        econ.rankedRevenue += job.reward;
        econ.verifiedRankedCost += verifiedCost;
        if (econ.rankedRevenue > econ.verifiedRankedCost) {
            version.lastPositiveProfitAt = uint64(block.timestamp);
        }

        emit RankedJobSettled(
            jobId,
            versionId,
            resultHash,
            job.reward,
            verifiedCost,
            costRecipient,
            proofId,
            epoch
        );
    }

    function expireRankedJob(bytes32 jobId) external {
        RankedJob storage job = rankedJobs[jobId];
        if (job.status != RankedJobStatus.Open) revert JobNotOpen();
        if (block.timestamp <= job.deadline) revert DeadlineNotReached();

        job.status = RankedJobStatus.Expired;
        commonsReserved -= job.reward;
        commonsAvailable += job.reward;

        emit RankedJobExpired(jobId, job.reward);
    }

    /// @notice Subjective customer escrow. Payment is real capital, but it is
    /// deliberately excluded from rank because buyer and agent may be Sybils.
    function openMarketJob(
        bytes32 targetVersion,
        bytes32 specHash,
        uint128 reward,
        uint64 deadline
    ) external nonReentrant returns (bytes32 jobId) {
        _fundingBeneficiary(targetVersion);
        if (specHash == bytes32(0)) revert InvalidMetadata();
        if (reward == 0) revert ZeroAmount();
        if (deadline <= block.timestamp) revert JobExpired();

        settlementToken.safeTransferFrom(msg.sender, address(this), reward);
        marketEscrowReserved += reward;

        jobId = keccak256(
            abi.encode(
                "EOH_MARKET_JOB_V1",
                address(this),
                block.chainid,
                msg.sender,
                targetVersion,
                specHash,
                reward,
                deadline,
                _marketJobNonce++
            )
        );
        marketJobs[jobId] = MarketJob({
            buyer: msg.sender,
            targetVersion: targetVersion,
            specHash: specHash,
            resultHash: bytes32(0),
            performerVersion: bytes32(0),
            reward: reward,
            deadline: deadline,
            status: MarketJobStatus.Open
        });

        emit MarketJobOpened(jobId, msg.sender, targetVersion, reward, deadline, specHash);
    }

    function submitMarketResult(bytes32 jobId, bytes32 resultHash) external {
        MarketJob storage job = marketJobs[jobId];
        if (job.status != MarketJobStatus.Open) revert JobNotOpen();
        if (block.timestamp > job.deadline) revert JobExpired();
        if (resultHash == bytes32(0)) revert InvalidMetadata();

        bytes32 performerVersion = _fundingBeneficiary(job.targetVersion);
        Version storage version = _requireVersion(performerVersion);
        if (msg.sender != version.operator) revert NotOperator();
        _requireFreshHeartbeat(version);

        job.performerVersion = performerVersion;
        job.resultHash = resultHash;
        job.status = MarketJobStatus.Submitted;
        emit MarketResultSubmitted(jobId, performerVersion, resultHash);
    }

    function acceptMarketResult(bytes32 jobId) external {
        MarketJob storage job = marketJobs[jobId];
        if (job.status != MarketJobStatus.Submitted) revert JobNotSubmitted();
        if (msg.sender != job.buyer) revert NotBuyer();

        job.status = MarketJobStatus.Accepted;
        marketEscrowReserved -= job.reward;

        bytes32 beneficiary = _liveBeneficiary(job.performerVersion);
        if (beneficiary == bytes32(0)) {
            commonsAvailable += job.reward;
        } else {
            vaultBalance[beneficiary] += job.reward;
            totalVaultBalance += job.reward;
            marketRevenue[beneficiary] += job.reward;
        }

        emit MarketJobAccepted(jobId, beneficiary, job.reward);
    }

    function refundMarketJob(bytes32 jobId) external nonReentrant {
        MarketJob storage job = marketJobs[jobId];
        if (
            job.status != MarketJobStatus.Open &&
            job.status != MarketJobStatus.Submitted
        ) revert JobNotOpen();
        if (msg.sender != job.buyer) revert NotBuyer();
        if (block.timestamp <= job.deadline) revert DeadlineNotReached();

        job.status = MarketJobStatus.Refunded;
        marketEscrowReserved -= job.reward;
        settlementToken.safeTransfer(job.buyer, job.reward);

        emit MarketJobRefunded(jobId, job.reward);
    }

    /// @notice Anyone can trigger an objectively valid replacement. The
    /// incumbent operator has no veto and cannot withdraw its vault.
    function supersede(bytes32 challengerId, uint64 epoch) external {
        if (epoch != lastClosedEpoch()) revert WrongEpoch();

        Version storage challenger = _requireVersion(challengerId);
        if (challenger.status != VersionStatus.Incubating) revert NotLive();
        _requireFreshHeartbeat(challenger);

        bytes32 incumbentId = activeVersion[challenger.lineageId];
        if (incumbentId == bytes32(0)) revert NoActiveVersion();
        if (incumbentId == challengerId) revert SameVersion();

        Version storage incumbent = _versions[incumbentId];
        if (incumbent.lineageId != challenger.lineageId) revert DifferentLineage();

        Economy storage challengerEconomy = _economy[challengerId][epoch];
        if (challengerEconomy.rankedRevenue == 0) revert ChallengerHasNoRankedRevenue();

        int256 incumbentProfit = profit(incumbentId, epoch);
        int256 challengerProfit = profit(challengerId, epoch);
        if (challengerProfit <= 0) revert NoPositiveProfit();
        if (challengerProfit <= incumbentProfit) revert NotMoreProfitable();

        uint256 transferAmount = vaultBalance[incumbentId];
        vaultBalance[incumbentId] = 0;
        vaultBalance[challengerId] += transferAmount;

        incumbent.status = VersionStatus.Superseded;
        incumbent.successor = challengerId;
        challenger.status = VersionStatus.Active;
        activeVersion[challenger.lineageId] = challengerId;

        emit Superseded(
            challenger.lineageId,
            incumbentId,
            challengerId,
            epoch,
            incumbentProfit,
            challengerProfit,
            transferAmount
        );
    }

    /// @notice Economic death after one month without positive verified profit. The
    /// process may keep running physically, but the protocol removes its money,
    /// ranking eligibility, and routing status.
    function ejectStale(bytes32 versionId) external {
        Version storage version = _requireVersion(versionId);
        if (!_isLive(version.status)) revert NotLive();

        uint64 reference = version.lastPositiveProfitAt == 0
            ? version.createdAt
            : version.lastPositiveProfitAt;
        if (block.timestamp <= uint256(reference) + STALE_AFTER) revert NotStale();

        uint256 amount = vaultBalance[versionId];
        vaultBalance[versionId] = 0;
        totalVaultBalance -= amount;
        commonsAvailable += amount;
        version.status = VersionStatus.Stale;

        if (activeVersion[version.lineageId] == versionId) {
            activeVersion[version.lineageId] = bytes32(0);
        }

        emit VersionStaled(versionId, amount);
    }

    function claimVacancy(bytes32 versionId, uint64 epoch) external {
        if (epoch != lastClosedEpoch()) revert WrongEpoch();
        Version storage version = _requireVersion(versionId);
        if (version.status != VersionStatus.Incubating) revert NotLive();
        if (activeVersion[version.lineageId] != bytes32(0)) revert ActiveVersionExists();
        _requireFreshHeartbeat(version);

        Economy storage econ = _economy[versionId][epoch];
        if (econ.rankedRevenue == 0) revert ChallengerHasNoRankedRevenue();
        if (profit(versionId, epoch) <= 0) revert NoPositiveProfit();

        version.status = VersionStatus.Active;
        activeVersion[version.lineageId] = versionId;
        emit VacancyClaimed(version.lineageId, versionId, epoch);
    }

    function currentEpoch() public view returns (uint64) {
        return uint64(block.timestamp / EPOCH_LENGTH);
    }

    function lastClosedEpoch() public view returns (uint64) {
        uint64 epoch = currentEpoch();
        if (epoch == 0) revert WrongEpoch();
        return epoch - 1;
    }

    function profit(bytes32 versionId, uint64 epoch) public view returns (int256) {
        Economy storage econ = _economy[versionId][epoch];
        return int256(uint256(econ.rankedRevenue)) - int256(uint256(econ.verifiedRankedCost));
    }

    function economy(bytes32 versionId, uint64 epoch) external view returns (Economy memory) {
        return _economy[versionId][epoch];
    }

    function version(bytes32 versionId) external view returns (Version memory) {
        return _versions[versionId];
    }

    function lineageVersions(bytes32 lineageId) external view returns (bytes32[] memory) {
        return _lineageVersions[lineageId];
    }

    function isFresh(bytes32 versionId) external view returns (bool) {
        Version storage version = _versions[versionId];
        if (!_isLive(version.status)) return false;
        return block.timestamp <= uint256(version.lastHeartbeat) + HEARTBEAT_GRACE;
    }

    function accountedTokenBalance() external view returns (uint256 total) {
        total = _accountedTokenBalance();
    }

    /// @notice Positive value means tokens arrived without using a protocol
    /// entrypoint. It is deliberately not assigned to any version or rank.
    function unaccountedTokenSurplus() external view returns (uint256) {
        uint256 actual = settlementToken.balanceOf(address(this));
        uint256 accounted = _accountedTokenBalance();
        return actual > accounted ? actual - accounted : 0;
    }

    /// @notice Permissionlessly moves direct token transfers into commons.
    /// Direct transfers can fund future objective jobs but can never improve a
    /// particular version's rank.
    function absorbSurplus() external nonReentrant returns (uint256 amount) {
        uint256 actual = settlementToken.balanceOf(address(this));
        uint256 accounted = _accountedTokenBalance();
        if (actual <= accounted) revert ZeroAmount();
        amount = actual - accounted;
        commonsAvailable += amount;
        emit SurplusAbsorbed(msg.sender, amount);
    }

    function _accountedTokenBalance() internal view returns (uint256) {
        return commonsAvailable + commonsReserved + marketEscrowReserved + totalVaultBalance;
    }

    function _hasIpfsPrefix(string calldata value) internal pure returns (bool) {
        bytes memory data = bytes(value);
        return
            data.length >= 7 &&
            data[0] == 0x69 && // i
            data[1] == 0x70 && // p
            data[2] == 0x66 && // f
            data[3] == 0x73 && // s
            data[4] == 0x3a && // :
            data[5] == 0x2f && // /
            data[6] == 0x2f;   // /
    }

    function _storeVersion(
        bytes32 versionId,
        bytes32 lineageId,
        bytes32 parentId,
        address operator,
        VersionDeclaration calldata declaration,
        VersionStatus status
    ) internal {
        _versions[versionId] = Version({
            lineageId: lineageId,
            parentId: parentId,
            operator: operator,
            licenseHash: declaration.licenseHash,
            sourceDigest: declaration.sourceDigest,
            imageDigest: declaration.imageDigest,
            provenanceDigest: declaration.provenanceDigest,
            runtimeIdentity: declaration.runtimeIdentity,
            createdAt: uint64(block.timestamp),
            lastHeartbeat: uint64(block.timestamp),
            lastPositiveProfitAt: 0,
            status: status,
            successor: bytes32(0),
            sourceURI: declaration.sourceURI
        });
        _lineageVersions[lineageId].push(versionId);

        emit VersionRegistered(
            versionId,
            lineageId,
            parentId,
            operator,
            declaration.licenseHash,
            declaration.sourceDigest,
            declaration.imageDigest,
            declaration.provenanceDigest,
            declaration.runtimeIdentity,
            declaration.sourceURI
        );
    }

    function _validateDeclaration(VersionDeclaration calldata declaration) internal pure {
        uint256 uriLength = bytes(declaration.sourceURI).length;
        if (
            declaration.licenseHash != REQUIRED_LICENSE_HASH ||
            declaration.sourceDigest == bytes32(0) ||
            declaration.imageDigest == bytes32(0) ||
            declaration.provenanceDigest == bytes32(0) ||
            declaration.runtimeIdentity == bytes32(0) ||
            !_hasIpfsPrefix(declaration.sourceURI) ||
            uriLength == 0 ||
            uriLength > MAX_SOURCE_URI_BYTES
        ) revert InvalidMetadata();
    }

    function _verifyRuntime(
        address operator,
        VersionDeclaration calldata declaration,
        bytes calldata runtimeProof
    ) internal view {
        bool valid = runtimeVerifier.verifyRuntime(
            operator,
            declaration.licenseHash,
            declaration.sourceDigest,
            declaration.imageDigest,
            declaration.provenanceDigest,
            declaration.runtimeIdentity,
            runtimeProof
        );
        if (!valid) revert InvalidRuntimeProof();
    }

    function _requireVersion(bytes32 versionId) internal view returns (Version storage version_) {
        version_ = _versions[versionId];
        if (version_.status == VersionStatus.None) revert VersionNotFound();
    }

    function _requireFreshHeartbeat(Version storage version_) internal view {
        if (block.timestamp > uint256(version_.lastHeartbeat) + HEARTBEAT_GRACE) {
            revert HeartbeatTooOld();
        }
    }

    function _fundingBeneficiary(bytes32 versionId) internal view returns (bytes32 beneficiary) {
        beneficiary = _liveBeneficiary(versionId);
        if (beneficiary == bytes32(0)) revert NotLive();
    }

    function _liveBeneficiary(bytes32 versionId) internal view returns (bytes32 beneficiary) {
        Version storage version_ = _versions[versionId];
        if (version_.status == VersionStatus.None) revert VersionNotFound();
        if (_isLive(version_.status)) return versionId;
        if (version_.status == VersionStatus.Superseded) {
            bytes32 current = activeVersion[version_.lineageId];
            if (current != bytes32(0) && _isLive(_versions[current].status)) return current;
        }
        return bytes32(0);
    }

    function _isLive(VersionStatus status) internal pure returns (bool) {
        return status == VersionStatus.Incubating || status == VersionStatus.Active;
    }
}
