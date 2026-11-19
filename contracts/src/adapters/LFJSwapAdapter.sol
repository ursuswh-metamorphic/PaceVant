// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {ISwapAdapter} from "../interfaces/ISwapAdapter.sol";
import {ILFJRouter, ILFJV1Factory, ILFJV1Pair} from "../interfaces/ILFJ.sol";

/// @notice Fuji-only, immutable direct V1 pool via LFJ LBRouter V2.2. No arbitrary paths/calls.
contract LFJSwapAdapter is ISwapAdapter, ReentrancyGuard {
    using SafeERC20 for IERC20;
    address public immutable authorizedVault;
    address public immutable usdc;
    address public immutable wavax;
    address public immutable lfjRouter;
    address public immutable pair;
    address public immutable factory;
    bytes32 public immutable routerCodeHash;
    bytes32 public immutable pairCodeHash;
    bytes32 public immutable inputCodeHash;
    bytes32 public immutable outputCodeHash;
    string public constant adapterVersion = "lfj-v1-fuji-v1";
    uint8 public constant routeVersion = 0; // Official ILBRouter.Version.V1
    uint256 public constant binStep = 0;
    error WrongChain();
    error UnsupportedPair();
    error BadRecipient();
    error InvalidRoute();
    error NoLiquidity();
    error UnexpectedTransfer();
    error MinOutputNotMet();

    constructor(address vault, address router, address pool, address input, address output) {
        if (block.chainid != 43113) revert WrongChain();
        if (vault.code.length == 0 || router.code.length == 0 || pool.code.length == 0
            || input == output || IERC20Metadata(input).decimals() != 6
            || IERC20Metadata(output).decimals() != 18) revert InvalidRoute();
        address f = ILFJRouter(router).getV1Factory();
        if (ILFJRouter(router).getWNATIVE() != output || ILFJV1Pair(pool).factory() != f
            || ILFJV1Factory(f).getPair(input, output) != pool) revert InvalidRoute();
        address t0 = ILFJV1Pair(pool).token0();
        address t1 = ILFJV1Pair(pool).token1();
        if (!((t0 == input && t1 == output) || (t0 == output && t1 == input))) revert UnsupportedPair();
        authorizedVault = vault; usdc = input; wavax = output;
        lfjRouter = router; pair = pool; factory = f;
        routerCodeHash = router.codehash; pairCodeHash = pool.codehash;
        inputCodeHash = input.codehash; outputCodeHash = output.codehash;
    }

    function _validate(address input, address output) private view {
        if (block.chainid != 43113) revert WrongChain();
        if (input != usdc || output != wavax) revert UnsupportedPair();
        if (lfjRouter.codehash != routerCodeHash || pair.codehash != pairCodeHash
            || usdc.codehash != inputCodeHash || wavax.codehash != outputCodeHash
            || ILFJRouter(lfjRouter).getV1Factory() != factory
            || ILFJV1Factory(factory).getPair(usdc, wavax) != pair) revert InvalidRoute();
    }

    function quote(address input, address output, uint256 amount) public view returns (uint256 result) {
        _validate(input, output);
        if (amount == 0 || amount > type(uint128).max) revert NoLiquidity();
        (uint112 r0, uint112 r1,) = ILFJV1Pair(pair).getReserves();
        (uint256 reserveIn, uint256 reserveOut) = ILFJV1Pair(pair).token0() == usdc ? (r0, r1) : (r1, r0);
        if (reserveIn == 0 || reserveOut == 0) revert NoLiquidity();
        // Official JoeLibrary.getAmountOut: V1 0.3% fee, actual pool reserves.
        uint256 withFee = amount * 997;
        result = withFee * reserveOut / (reserveIn * 1000 + withFee);
        if (result == 0 || result >= reserveOut) revert NoLiquidity();
    }

    function exactInput(address input, address output, uint256 amount, uint256 minOut, address recipient)
        external nonReentrant returns (uint256 amountOut)
    {
        if (msg.sender != authorizedVault || recipient != authorizedVault) revert BadRecipient();
        _validate(input, output);
        if (minOut == 0 || quote(input, output, amount) < minOut) revert MinOutputNotMet();
        IERC20 token = IERC20(input);
        uint256 beforeIn = token.balanceOf(address(this));
        uint256 beforeOut = IERC20(output).balanceOf(recipient);
        token.safeTransferFrom(msg.sender, address(this), amount);
        if (token.balanceOf(address(this)) - beforeIn != amount) revert UnexpectedTransfer();
        ILFJRouter.Path memory path;
        path.pairBinSteps = new uint256[](1);
        path.versions = new ILFJRouter.Version[](1);
        path.tokenPath = new address[](2);
        path.versions[0] = ILFJRouter.Version.V1;
        path.tokenPath[0] = input; path.tokenPath[1] = output;
        token.forceApprove(lfjRouter, amount);
        uint256 reported = ILFJRouter(lfjRouter).swapExactTokensForTokens(amount, minOut, path, recipient, block.timestamp);
        token.forceApprove(lfjRouter, 0);
        if (token.balanceOf(address(this)) != beforeIn) revert UnexpectedTransfer();
        uint256 afterOut = IERC20(output).balanceOf(recipient);
        if (afterOut < beforeOut || afterOut - beforeOut < minOut) revert MinOutputNotMet();
        amountOut = afterOut - beforeOut;
        if (amountOut != reported) revert UnexpectedTransfer();
    }
}
