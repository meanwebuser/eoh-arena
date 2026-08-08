// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

import {IRuntimeVerifier} from "../interfaces/IRuntimeVerifier.sol";

/// @notice TEST ONLY. Checks deterministic proof formatting but provides no TEE
/// or zkVM security. Replace this contract before any deployment with value.
contract DemoRuntimeVerifier is IRuntimeVerifier {
    function verifyRuntime(
        address operator,
        bytes32 licenseHash,
        bytes32 sourceDigest,
        bytes32 imageDigest,
        bytes32 provenanceDigest,
        bytes32 runtimeIdentity,
        bytes calldata proof
    ) external pure returns (bool valid) {
        bytes32 expected = keccak256(
            abi.encode(
                keccak256("EOH_DEMO_RUNTIME_PROOF_V1"),
                operator,
                licenseHash,
                sourceDigest,
                imageDigest,
                provenanceDigest,
                runtimeIdentity
            )
        );
        valid = proof.length == 32 && abi.decode(proof, (bytes32)) == expected;
    }

    function verifyHeartbeat(
        bytes32 versionId,
        bytes32 runtimeIdentity,
        bytes32 stateHash,
        uint64 observedAt,
        bytes calldata proof
    ) external pure returns (bool valid) {
        bytes32 expected = keccak256(
            abi.encode(
                keccak256("EOH_DEMO_HEARTBEAT_PROOF_V1"),
                versionId,
                runtimeIdentity,
                stateHash,
                observedAt
            )
        );
        valid = proof.length == 32 && abi.decode(proof, (bytes32)) == expected;
    }
}
