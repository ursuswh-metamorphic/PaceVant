// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ISwapAdapter} from "./interfaces/ISwapAdapter.sol";

/// @notice PDR-enforced test treasury. No arbitrary calls; not an ERC-4337 account.
contract PolicyVault is Ownable, Pausable, ReentrancyGuard, EIP712 {
    using SafeERC20 for IERC20;
    struct Approval {
        bytes32 policyHash;
        bytes32 evidenceRoot;
        address router;
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint256 minAmountOut;
        bytes32 calldataHash;
        uint256 nonce;
        uint256 deadline;
    }
    bytes32 public constant APPROVAL_TYPEHASH = keccak256("Approval(bytes32 policyHash,bytes32 evidenceRoot,address router,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,bytes32 calldataHash,uint256 nonce,uint256 deadline)");
    address public immutable usdc;
    address public immutable wavax;
    address public attestor;
    bytes32 public activePolicyHash;
    uint256 public policyVersion;
    uint256 public policyExpiresAt;
    uint256 public maxPerSwap;
    uint256 public maxSpendPerDay;
    uint256 public maxSlippageBps;
    uint256 public maxApprovalTtl = 30;
    bool public policyActive;
    mapping(address => bool) public allowedRouters;
    mapping(address => bool) public allowedTokens;
    mapping(uint256 => bool) public usedNonce;
    mapping(uint256 => uint256) public dailySpentUsdc;
    error InvalidConfiguration();
    error PolicyRevoked();
    error BadSignature();
    error NonceReplay();
    error ExpiredApproval();
    error HashMismatch();
    error InvalidCall();
    error TradeSizeLimit();
    error DailySpendLimit();
    error UnexpectedTransfer();
    error MinOutputNotMet();
    event PolicyUpdated(bytes32 indexed policyHash, uint256 version);
    event AttestorUpdated(address indexed attestor);
    event RouterUpdated(address indexed router, bool allowed);
    event TokenUpdated(address indexed token, bool allowed);
    event Withdrawn(address indexed token, address indexed recipient, uint256 amount);
    event SwapExecuted(uint256 indexed nonce, bytes32 indexed policyHash, bytes32 evidenceRoot,
        address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut);

    constructor(address admin, address signer, address input, address output)
        Ownable(admin) EIP712("TreasuryPolicyVault", "1")
    {
        if (signer == address(0) || signer == admin || input == output || input.code.length == 0 || output.code.length == 0)
            revert InvalidConfiguration();
        usdc = input; wavax = output; attestor = signer;
        allowedTokens[input] = true; allowedTokens[output] = true;
    }
    function _invalidate() internal { policyActive = false; emit PolicyUpdated(activePolicyHash, ++policyVersion); }
    function configurePolicy(bytes32 commitment, uint256 perSwap, uint256 perDay, uint256 slippageBps, uint256 expiresAt)
        external onlyOwner
    {
        // Never reactivate a previous hash: signatures from older configurations must stay invalid.
        if (commitment == bytes32(0) || perSwap == 0 || perDay < perSwap || slippageBps > 10000 || expiresAt <= block.timestamp)
            revert InvalidConfiguration();
        ++policyVersion;
        activePolicyHash = keccak256(abi.encode(commitment, policyVersion, address(this), block.chainid,
            attestor, perSwap, perDay, slippageBps, expiresAt));
        maxPerSwap = perSwap; maxSpendPerDay = perDay; maxSlippageBps = slippageBps;
        policyExpiresAt = expiresAt; policyActive = true; emit PolicyUpdated(activePolicyHash, policyVersion);
    }
    function setAttestor(address signer) external onlyOwner {
        if (signer == owner() || (signer != address(0) && signer.code.length != 0)) revert InvalidConfiguration();
        attestor = signer; _invalidate(); emit AttestorUpdated(signer);
    }
    function setRouter(address router, bool allowed) external onlyOwner {
        if (allowed && router.code.length == 0) revert InvalidConfiguration();
        allowedRouters[router] = allowed; _invalidate(); emit RouterUpdated(router, allowed);
    }
    function setToken(address token, bool allowed) external onlyOwner {
        if (token != usdc && token != wavax) revert InvalidConfiguration();
        allowedTokens[token] = allowed; _invalidate(); emit TokenUpdated(token, allowed);
    }
    function revokePolicy() external onlyOwner { _invalidate(); }
    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }
    function withdraw(address token, address to, uint256 amount) external onlyOwner nonReentrant whenPaused {
        if (to == address(0)) revert InvalidConfiguration();
        _invalidate(); IERC20(token).safeTransfer(to, amount); emit Withdrawn(token, to, amount);
    }
    function hashApproval(Approval calldata a) public view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(APPROVAL_TYPEHASH, a)));
    }
    function executeApprovedSwap(Approval calldata a, bytes calldata data, bytes calldata signature)
        external nonReentrant whenNotPaused
    {
        if (!policyActive || a.policyHash != activePolicyHash || block.timestamp > policyExpiresAt) revert PolicyRevoked();
        if (a.deadline < block.timestamp || a.deadline > block.timestamp + maxApprovalTtl) revert ExpiredApproval();
        if (usedNonce[a.nonce]) revert NonceReplay();
        if (attestor == address(0) || ECDSA.recover(hashApproval(a), signature) != attestor) revert BadSignature();
        if (a.evidenceRoot == bytes32(0) || keccak256(data) != a.calldataHash) revert HashMismatch();
        if (!allowedRouters[a.router] || !allowedTokens[a.tokenIn] || !allowedTokens[a.tokenOut]
            || a.tokenIn != usdc || a.tokenOut != wavax || data.length != 164
            || bytes4(data[:4]) != ISwapAdapter.exactInput.selector) revert InvalidCall();
        (address input, address output, uint256 amount, uint256 minOut, address recipient) =
            abi.decode(data[4:], (address, address, uint256, uint256, address));
        if (input != a.tokenIn || output != a.tokenOut || amount != a.amountIn || minOut != a.minAmountOut
            || recipient != address(this) || minOut == 0 || keccak256(data) != keccak256(abi.encodeCall(
                ISwapAdapter.exactInput, (input, output, amount, minOut, recipient)))) revert InvalidCall();
        if (amount == 0 || amount > maxPerSwap) revert TradeSizeLimit();
        uint256 day = block.timestamp / 1 days;
        if (dailySpentUsdc[day] + amount > maxSpendPerDay) revert DailySpendLimit();
        usedNonce[a.nonce] = true; dailySpentUsdc[day] += amount;
        uint256 beforeIn = IERC20(input).balanceOf(address(this));
        uint256 beforeOut = IERC20(output).balanceOf(address(this));
        IERC20(input).forceApprove(a.router, amount);
        ISwapAdapter(a.router).exactInput(input, output, amount, minOut, address(this));
        IERC20(input).forceApprove(a.router, 0);
        uint256 afterIn = IERC20(input).balanceOf(address(this));
        uint256 afterOut = IERC20(output).balanceOf(address(this));
        if (afterIn > beforeIn || beforeIn - afterIn != amount) revert UnexpectedTransfer();
        if (afterOut < beforeOut || afterOut - beforeOut < minOut) revert MinOutputNotMet();
        emit SwapExecuted(a.nonce, a.policyHash, a.evidenceRoot, input, output, amount, afterOut - beforeOut);
    }
}
