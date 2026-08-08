// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

/// @notice Decides whether a ranked job belongs to the immutable, public task
/// schedule. Anyone may relay an authorized job; no privileged EOA is required.
interface IJobAuthorizer {
    function authorizeJob(
        bytes32 specHash,
        address verifier,
        uint128 reward,
        uint64 deadline,
        bytes calldata proof
    ) external view returns (bool valid, bytes32 authorizationId);
}
