// SPDX-License-Identifier: AGPL-3.0-or-later
pragma solidity 0.8.36;

interface IERC20Minimal {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}
