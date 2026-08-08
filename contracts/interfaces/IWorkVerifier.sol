// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

/// @notice Verifies both a ranked result and the protocol-visible cost needed
/// to produce it. The verifier is part of the protocol trust boundary.
interface IWorkVerifier {
    /// @return valid Whether the result/proof is accepted.
    /// @return proofId Globally unique identifier used for replay protection.
    /// @return verifiedCost Cost, denominated in settlement-token base units.
    /// @return costRecipient Address that must receive verifiedCost atomically.
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
    );
}
