// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

/// @notice Verifies an operating expense before protocol-held agent capital can
/// leave the arena. It prevents an operator from simply withdrawing the vault.
interface IExpenseVerifier {
    function verifyExpense(
        bytes32 versionId,
        bytes32 expenseId,
        address recipient,
        uint128 amount,
        bytes32 payloadHash,
        bytes calldata proof
    ) external view returns (bool valid, bytes32 proofId);
}
