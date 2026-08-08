// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

import {IWorkVerifier} from "../interfaces/IWorkVerifier.sol";

/// @notice Minimal objective verifier for demos and deterministic benchmarks.
/// It accepts exactly one spec hash and one result hash, and atomically charges
/// a fixed provider cost. It is not a verifier for arbitrary AI output.
contract FixedCostHashVerifier is IWorkVerifier {
    bytes32 public immutable expectedSpecHash;
    bytes32 public immutable expectedResultHash;
    uint128 public immutable fixedCost;
    address public immutable fixedCostRecipient;

    constructor(
        bytes32 expectedSpecHash_,
        bytes32 expectedResultHash_,
        uint128 fixedCost_,
        address fixedCostRecipient_
    ) {
        require(expectedSpecHash_ != bytes32(0), "spec=0");
        require(expectedResultHash_ != bytes32(0), "result=0");
        require(fixedCost_ == 0 || fixedCostRecipient_ != address(0), "recipient=0");
        expectedSpecHash = expectedSpecHash_;
        expectedResultHash = expectedResultHash_;
        fixedCost = fixedCost_;
        fixedCostRecipient = fixedCostRecipient_;
    }

    function verify(
        bytes32 jobId,
        bytes32 versionId,
        bytes32 specHash,
        bytes32 resultHash,
        bytes calldata proof
    ) external view returns (
        bool valid,
        bytes32 proofId,
        uint128 verifiedCost,
        address costRecipient
    ) {
        valid = specHash == expectedSpecHash && resultHash == expectedResultHash;
        proofId = keccak256(
            abi.encode(
                keccak256("EOH_FIXED_HASH_PROOF_V1"),
                address(this),
                jobId,
                versionId,
                specHash,
                resultHash,
                keccak256(proof)
            )
        );
        verifiedCost = fixedCost;
        costRecipient = fixedCostRecipient;
    }
}
