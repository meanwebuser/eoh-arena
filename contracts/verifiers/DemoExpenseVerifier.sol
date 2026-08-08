// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

import {IExpenseVerifier} from "../interfaces/IExpenseVerifier.sol";

/// @notice TEST ONLY. Demonstrates the expense-verifier interface but does not
/// authenticate a real provider. Production must verify provider signatures or
/// a stronger receipt/attestation.
contract DemoExpenseVerifier is IExpenseVerifier {
    function verifyExpense(
        bytes32 versionId,
        bytes32 expenseId,
        address recipient,
        uint128 amount,
        bytes32 payloadHash,
        bytes calldata proof
    ) external pure returns (bool valid, bytes32 proofId) {
        proofId = keccak256(
            abi.encode(
                keccak256("EOH_DEMO_EXPENSE_V1"),
                versionId,
                expenseId,
                recipient,
                amount,
                payloadHash
            )
        );
        valid = proof.length == 32 && abi.decode(proof, (bytes32)) == proofId;
    }
}
