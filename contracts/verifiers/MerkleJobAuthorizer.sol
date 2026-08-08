// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

import {IJobAuthorizer} from "../interfaces/IJobAuthorizer.sol";

/// @notice Governance-free ranked-job schedule committed by an immutable Merkle
/// root. A new schedule requires a new authorizer (and normally a new arena
/// release); no EOA can insert a favorable task after deployment.
contract MerkleJobAuthorizer is IJobAuthorizer {
    bytes32 public immutable root;

    constructor(bytes32 root_) {
        require(root_ != bytes32(0), "root=0");
        root = root_;
    }

    function leafFor(
        bytes32 specHash,
        address verifier,
        uint128 reward,
        uint64 deadline
    ) public pure returns (bytes32) {
        return keccak256(
            abi.encode(
                keccak256("EOH_JOB_AUTH_V1"),
                specHash,
                verifier,
                reward,
                deadline
            )
        );
    }

    function authorizeJob(
        bytes32 specHash,
        address verifier,
        uint128 reward,
        uint64 deadline,
        bytes calldata proof
    ) external view returns (bool valid, bytes32 authorizationId) {
        authorizationId = leafFor(specHash, verifier, reward, deadline);
        bytes32[] memory siblings = abi.decode(proof, (bytes32[]));
        bytes32 computed = authorizationId;
        for (uint256 i = 0; i < siblings.length; ++i) {
            bytes32 sibling = siblings[i];
            computed = computed < sibling
                ? keccak256(abi.encodePacked(computed, sibling))
                : keccak256(abi.encodePacked(sibling, computed));
        }
        valid = computed == root;
    }
}
