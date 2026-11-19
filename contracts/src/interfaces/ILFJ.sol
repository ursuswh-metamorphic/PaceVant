// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// Minimal ABI subset of traderjoe-xyz/joe-v2 ILBRouter (MIT), plus Joe V1 pair/factory.
// Version ordinal values and Path ordering MUST match the official LBRouter ABI.
interface ILFJRouter {
    enum Version { V1, V2, V2_1, V2_2 }
    struct Path { uint256[] pairBinSteps; Version[] versions; address[] tokenPath; }
    function getV1Factory() external view returns (address);
    function getWNATIVE() external view returns (address);
    function swapExactTokensForTokens(uint256 amountIn, uint256 amountOutMin, Path calldata path,
        address to, uint256 deadline) external returns (uint256 amountOut);
}
interface ILFJV1Factory {
    function getPair(address, address) external view returns (address);
}
interface ILFJV1Pair {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function factory() external view returns (address);
    function getReserves() external view returns (uint112, uint112, uint32);
}
