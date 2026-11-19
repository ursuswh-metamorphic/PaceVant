// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";
import {ISwapAdapter} from "../interfaces/ISwapAdapter.sol";

/// @notice Controlled test liquidity, NOT an AMM or a real MEV reproduction.
contract MockSwapAdapter is Ownable, ISwapAdapter {
    using SafeERC20 for IERC20;
    address public immutable usdc;
    address public immutable wavax;
    uint256 public outputPerUsdc = 5e16; // $20/WAVAX: 1 USDC -> .05 WAVAX
    error UnsupportedPair();
    error MinOutputNotMet();
    error BadRecipient();
    event TestPriceUpdated(uint256 outputPerUsdc);
    constructor(address admin, address input, address output) Ownable(admin) { usdc = input; wavax = output; }
    function setOutputPerUsdc(uint256 value) external onlyOwner {
        require(value > 0, "ZERO_PRICE"); outputPerUsdc = value; emit TestPriceUpdated(value);
    }
    function quote(address input, address output, uint256 amount) public view returns (uint256) {
        if (input == usdc && output == wavax) return Math.mulDiv(amount, outputPerUsdc, 1e6);
        if (input == wavax && output == usdc) return Math.mulDiv(amount, 1e6, outputPerUsdc);
        revert UnsupportedPair();
    }
    function exactInput(address input, address output, uint256 amount, uint256 minOut, address recipient)
        external returns (uint256 result)
    {
        if (recipient != msg.sender) revert BadRecipient();
        result = quote(input, output, amount);
        if (result < minOut) revert MinOutputNotMet();
        IERC20(input).safeTransferFrom(msg.sender, address(this), amount);
        IERC20(output).safeTransfer(recipient, result);
    }
}
