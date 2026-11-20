// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {ERC4626} from "@openzeppelin/contracts/token/ERC20/extensions/ERC4626.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
/// @notice LOCAL DEMONSTRATION ONLY. No strategy, yield promise, or public integration.
contract DemoERC4626 is ERC4626 {
    bool public stopped;
    constructor(IERC20 asset_) ERC20("LOCAL DEMO USDC shares", "demoUSDC") ERC4626(asset_) {}
    function setStopped(bool value) external { stopped = value; }
    function maxDeposit(address) public view override returns(uint256) { return stopped ? 0 : type(uint256).max; }
    function maxRedeem(address holder) public view override returns(uint256) { return stopped ? 0 : balanceOf(holder); }
}
