// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

import {IERC20Minimal} from "../interfaces/IERC20Minimal.sol";

library SafeTransfer {
    error TokenTransferFailed();

    function safeTransfer(IERC20Minimal token, address to, uint256 amount) internal {
        (bool ok, bytes memory data) = address(token).call(
            abi.encodeCall(IERC20Minimal.transfer, (to, amount))
        );
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) {
            revert TokenTransferFailed();
        }
    }

    function safeTransferFrom(
        IERC20Minimal token,
        address from,
        address to,
        uint256 amount
    ) internal {
        (bool ok, bytes memory data) = address(token).call(
            abi.encodeCall(IERC20Minimal.transferFrom, (from, to, amount))
        );
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) {
            revert TokenTransferFailed();
        }
    }
}
