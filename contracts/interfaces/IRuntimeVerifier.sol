// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

/// @notice Verifies that a runtime identity is bound to the declared source,
/// reproducible-build artifact, provenance statement, and live heartbeats.
/// @dev A production implementation can verify a TEE quote, zkVM proof, or
/// another objective attestation. A maintainer signature alone is not enough.
interface IRuntimeVerifier {
    function verifyRuntime(
        address operator,
        bytes32 licenseHash,
        bytes32 sourceDigest,
        bytes32 imageDigest,
        bytes32 provenanceDigest,
        bytes32 runtimeIdentity,
        bytes calldata proof
    ) external view returns (bool valid);

    /// @notice Verifies that a live runtime with the registered identity emitted
    /// the state commitment for this exact version and observation time.
    function verifyHeartbeat(
        bytes32 versionId,
        bytes32 runtimeIdentity,
        bytes32 stateHash,
        uint64 observedAt,
        bytes calldata proof
    ) external view returns (bool valid);
}
