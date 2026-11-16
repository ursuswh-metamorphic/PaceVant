// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface ISwapAdapter {
    function quote(address tokenIn, address tokenOut, uint256 amountIn) external view returns (uint256);
    function exactInput(address tokenIn, address tokenOut, uint256 amountIn, uint256 minOut, address recipient)
        external returns (uint256 amountOut);
}
