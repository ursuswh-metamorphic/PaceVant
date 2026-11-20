// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {PolicyVault} from "./PolicyVault.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC4626} from "@openzeppelin/contracts/interfaces/IERC4626.sol";
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {ISwapAdapter} from "./interfaces/ISwapAdapter.sol";

/// @notice Explicit new deployment. Fixed calls only; V1/V2 execution is permanently disabled.
contract PolicyVaultV3 is PolicyVault {
    using SafeERC20 for IERC20;
    // 1 swap, 2 payment, 3 deposit assets, 4 redeem shares. Rebalance is a bounded swap.
    struct Operation {
        uint8 kind;
        bool rebalance;
        bytes32 policyHash;
        bytes32 sessionId;
        bytes32 intentHash;
        bytes32 evidenceRoot;
        bytes32 proofContextHash;
        bytes32 constraintsHash;
        bytes32 calldataHash;
        address target;
        address tokenIn;
        address tokenOut;
        address recipient;
        uint256 amount;
        uint256 minOutput;
        uint256 spendDebitUsdE8;
        uint256 riskDebitUsdE8;
        uint256 nonce;
        uint256 deadline;
    }
    bytes32 public constant OPERATION_TYPEHASH = keccak256("Operation(uint8 kind,bool rebalance,bytes32 policyHash,bytes32 sessionId,bytes32 intentHash,bytes32 evidenceRoot,bytes32 proofContextHash,bytes32 constraintsHash,bytes32 calldataHash,address target,address tokenIn,address tokenOut,address recipient,uint256 amount,uint256 minOutput,uint256 spendDebitUsdE8,uint256 riskDebitUsdE8,uint256 nonce,uint256 deadline)");
    // Fixed registry order: USDC, WAVAX, approved shares, native AVAX. No omitted assets.
    struct Constraints {
        uint256[4] beforeBalances;
        int256[4] minDeltas;
        uint256 receiptCredit;
        uint256 maxWavaxBalance;
    }
    struct Authority {
        uint256 operationMask;
        uint256 spendLimitUsdE8;
        uint256 spendUsedUsdE8;
        uint256 maxActions;
        uint256 actions;
        uint256 cooldown;
        uint256 lastRebalance;
    }
    struct PayeeLimit { uint256 perPayment; uint256 perDay; }
    IERC4626 public approvedVault;
    bytes32 public vaultCodeHash;
    bytes32 public adapterCodeHash;
    bytes32 public usdcCodeHash;
    bytes32 public wavaxCodeHash;
    uint256 public shareUnit;
    uint256 public minAssetsPerShare;
    uint256 public maxAssetsPerShare;
    uint256 public maxOperationUsdE8;
    uint256 public maxDailySpendUsdE8;
    uint256 public maxVaultAssets;
    uint256 public maxVaultShares;
    uint256 public maxWavaxExposureBps;
    mapping(bytes32 => Authority) public authorities;
    mapping(address => mapping(address => PayeeLimit)) public payees;
    mapping(bytes32 => uint256) public payeeDailySpent;
    mapping(uint256 => uint256) public dailySpentUsdE8;
    error ScopeViolation();
    error PayeeNotAllowed();
    error ReceiptNotMet();
    error CodeIdentityChanged();
    error VaultRateOutOfBounds();
    error StateDrift();
    event OperationExecuted(uint256 indexed nonce, bytes32 indexed sessionId, uint8 kind,
        bytes32 evidenceRoot, bytes32 proofContextHash, int256[4] deltas, uint256 received);
    event V3Configured(address indexed vault, bytes32 codeHash);
    event PayeeConfigured(address indexed token, address indexed payee, uint256 perPayment, uint256 perDay);
    event AuthorityConfigured(bytes32 indexed sessionId, uint256 mask, uint256 spendLimit, uint256 maxActions, uint256 cooldown);

    constructor(address admin, address signer, address input, address output)
        PolicyVault(admin, signer, input, output) {}
    receive() external payable {}

    function executeApprovedSwap(Approval calldata, bytes calldata, bytes calldata) external pure override {
        revert ProofRequired();
    }
    function executeApprovedSwapV2(ApprovalV2 calldata, bytes calldata, PostConditionsV2 calldata, bytes calldata)
        external pure override { revert ProofRequired(); }

    /// @dev Every change invalidates policy AND existing sessions through policy hash rotation.
    function configureV3(address vault, uint256 rateLow, uint256 rateHigh, uint256 perOperationUsdE8,
        uint256 dailyUsdE8, uint256 assetCap, uint256 shareCap, uint256 exposureBps) external virtual onlyOwner
    {
        if (!v2Enabled || vault.code.length == 0 || vault == usdc || vault == wavax
            || IERC4626(vault).asset() != usdc || IERC20Metadata(vault).decimals() > 18
            || rateLow == 0 || rateHigh < rateLow || perOperationUsdE8 == 0 || dailyUsdE8 < perOperationUsdE8
            || assetCap == 0 || shareCap == 0 || exposureBps > 10000) revert InvalidConfiguration();
        approvedVault = IERC4626(vault); vaultCodeHash = vault.codehash;
        adapterCodeHash = proofAdapter.codehash;
        usdcCodeHash = usdc.codehash; wavaxCodeHash = wavax.codehash;
        shareUnit = 10 ** IERC20Metadata(vault).decimals();
        minAssetsPerShare = rateLow; maxAssetsPerShare = rateHigh;
        maxOperationUsdE8 = perOperationUsdE8; maxDailySpendUsdE8 = dailyUsdE8;
        maxVaultAssets = assetCap; maxVaultShares = shareCap; maxWavaxExposureBps = exposureBps;
        _checkCodeAndRate(); _invalidate(); emit V3Configured(vault, vaultCodeHash);
    }
    function setPayee(address token, address recipient, uint256 perPayment, uint256 perDay) external virtual onlyOwner {
        // EOA payees exclude callbacks and counterfactual contracts at execution time.
        if ((token != usdc && token != wavax && token != address(0)) || recipient == address(0)
            || recipient == address(this) || recipient.code.length != 0 || perDay < perPayment)
            revert InvalidConfiguration();
        payees[token][recipient] = PayeeLimit(perPayment, perDay);
        _invalidate(); emit PayeeConfigured(token, recipient, perPayment, perDay);
    }
    function authorizeSession(bytes32 id, uint256 mask, uint256 spendLimit, uint256 maxActions, uint256 cooldown)
        external virtual onlyOwner
    {
        Session storage s = sessions[id];
        if (!s.active || s.policyHash != activePolicyHash || mask == 0 || mask > 31
            || spendLimit == 0 || maxActions == 0 || authorities[id].operationMask != 0)
            revert InvalidConfiguration();
        authorities[id] = Authority(mask, spendLimit, 0, maxActions, 0, cooldown, 0);
        emit AuthorityConfigured(id, mask, spendLimit, maxActions, cooldown);
    }
    function _checkCodeAndRate() internal view virtual {
        address v = address(approvedVault);
        if (v == address(0) || v.codehash != vaultCodeHash || proofAdapter.codehash != adapterCodeHash
            || usdc.codehash != usdcCodeHash || wavax.codehash != wavaxCodeHash || approvedVault.asset() != usdc)
            revert CodeIdentityChanged();
        uint256 rate = approvedVault.convertToAssets(shareUnit);
        if (rate < minAssetsPerShare || rate > maxAssetsPerShare) revert VaultRateOutOfBounds();
    }
    function balances() public view virtual returns (uint256[4] memory b) {
        b[0] = IERC20(usdc).balanceOf(address(this)); b[1] = IERC20(wavax).balanceOf(address(this));
        b[2] = approvedVault.balanceOf(address(this)); b[3] = address(this).balance;
    }
    function hashOperation(Operation calldata a) public view returns (bytes32) {
        bytes32 domain = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256("TreasuryPolicyVault"), keccak256("3"), block.chainid, address(this)));
        return keccak256(abi.encodePacked(hex"1901", domain, keccak256(abi.encode(OPERATION_TYPEHASH, a))));
    }
    function operationCall(Operation calldata a) public view returns (address target, uint256 value, bytes memory data) {
        if (a.kind == 1) return (a.target, 0, abi.encodeCall(ISwapAdapter.exactInput,
            (a.tokenIn, a.tokenOut, a.amount, a.minOutput, address(this))));
        if (a.kind == 2) return (a.tokenIn == address(0) ? a.recipient : a.tokenIn,
            a.tokenIn == address(0) ? a.amount : 0,
            a.tokenIn == address(0) ? bytes("") : abi.encodeCall(IERC20.transfer, (a.recipient, a.amount)));
        if (a.kind == 3) return (a.target, 0, abi.encodeCall(IERC4626.deposit, (a.amount, address(this))));
        if (a.kind == 4) return (a.target, 0, abi.encodeCall(IERC4626.redeem, (a.amount, address(this), address(this))));
        revert InvalidCall();
    }
    function _validateCall(Operation calldata a, Constraints calldata phi) internal view virtual {
        if (a.amount == 0 || a.amount > uint256(type(int256).max) || a.minOutput > uint256(type(int256).max)) revert InvalidCall();
        if (a.rebalance && a.kind != 1) revert InvalidCall();
        if (a.kind == 1) {
            if (a.target != proofAdapter || !allowedRouters[a.target] || !allowedTokens[a.tokenIn]
                || !allowedTokens[a.tokenOut] || a.tokenIn == a.tokenOut || a.recipient != address(this)
                || (a.tokenIn != usdc && a.tokenIn != wavax) || (a.tokenOut != usdc && a.tokenOut != wavax)
                || a.minOutput == 0 || a.amount > (a.tokenIn == usdc ? maxPerSwap : proofPolicy.maxWavaxPerSwap)) revert InvalidCall();
        } else if (a.kind == 2) {
            if ((a.tokenIn != usdc && a.tokenIn != wavax && a.tokenIn != address(0))
                || (a.tokenIn != address(0) && !allowedTokens[a.tokenIn]) || a.tokenOut != a.tokenIn
                || a.target != (a.tokenIn == address(0) ? a.recipient : a.tokenIn)
                || a.recipient == address(this) || a.recipient.code.length != 0) revert InvalidCall();
            PayeeLimit memory p = payees[a.tokenIn][a.recipient];
            if (p.perPayment == 0 || a.amount > p.perPayment) revert PayeeNotAllowed();
            if (phi.receiptCredit == 0 || phi.receiptCredit > a.amount || a.minOutput != phi.receiptCredit) revert ReceiptNotMet();
        } else if (a.kind == 3 || a.kind == 4) {
            if (a.target != address(approvedVault) || a.recipient != address(this) || !allowedTokens[usdc]
                || a.tokenIn != (a.kind == 3 ? usdc : address(approvedVault))
                || a.tokenOut != (a.kind == 3 ? address(approvedVault) : usdc) || a.minOutput == 0
                || a.amount > (a.kind == 3 ? maxVaultAssets : maxVaultShares)) revert InvalidCall();
        } else revert InvalidCall();
        if (a.kind != 2 && phi.receiptCredit != 0) revert InvalidPostConditions();
        (address target, uint256 value, bytes memory data) = operationCall(a);
        if (a.calldataHash != keccak256(abi.encode(target, value, data))) revert HashMismatch();
        uint256 inputIndex = a.tokenIn == usdc ? 0 : a.tokenIn == wavax ? 1 : a.tokenIn == address(approvedVault) ? 2 : 3;
        uint256 outputIndex = a.tokenOut == usdc ? 0 : a.tokenOut == wavax ? 1 : a.tokenOut == address(approvedVault) ? 2 : 3;
        for (uint256 i; i < 4; ++i) {
            if (i == inputIndex) { if (phi.minDeltas[i] != -int256(a.amount)) revert InvalidPostConditions(); }
            else if (a.kind != 2 && i == outputIndex) {
                if (phi.minDeltas[i] < int256(a.minOutput)) revert InvalidPostConditions();
            } else if (phi.minDeltas[i] < 0) revert InvalidPostConditions();
        }
        // USD accounting uses conservative upper prices off-chain; USDC has an independent nominal floor.
        if (a.tokenIn == usdc && a.spendDebitUsdE8 < a.amount * 100) revert TradeSizeLimit();
        if (a.spendDebitUsdE8 == 0 || a.spendDebitUsdE8 > _maxOperationDebit(a)) revert TradeSizeLimit();
    }
    function executeOperation(Operation calldata a, Constraints calldata phi, bytes calldata signature)
        external nonReentrant whenNotPaused
    {
        if (!v2Enabled || !policyActive || a.policyHash != activePolicyHash || block.timestamp > policyExpiresAt) revert PolicyRevoked();
        if (a.deadline < block.timestamp || a.deadline > block.timestamp + maxApprovalTtl || a.deadline > policyExpiresAt) revert ExpiredApproval();
        if (usedNonce[a.nonce]) revert NonceReplay();
        if (attestor == address(0) || ECDSA.recover(hashOperation(a), signature) != attestor) revert BadSignature();
        if (a.intentHash == bytes32(0) || a.evidenceRoot == bytes32(0) || a.proofContextHash == bytes32(0)
            || a.constraintsHash != keccak256(abi.encode(phi))) revert HashMismatch();
        _checkCodeAndRate(); _validateCall(a, phi);
        Session storage s = sessions[a.sessionId]; Authority storage auth = authorities[a.sessionId];
        uint256 spendDebit = _spendDebit(a);
        if (!s.active || s.policyHash != activePolicyHash || block.timestamp < s.startsAt
            || block.timestamp > s.expiresAt || a.deadline > s.expiresAt) revert SessionUnavailable();
        if ((auth.operationMask & (1 << (a.kind - 1))) == 0 || auth.actions >= auth.maxActions
            || auth.spendUsedUsdE8 + spendDebit > auth.spendLimitUsdE8) revert ScopeViolation();
        if (a.rebalance && ((auth.operationMask & 16) == 0 || (auth.lastRebalance != 0
            && block.timestamp < auth.lastRebalance + auth.cooldown))) revert ScopeViolation();
        if (s.riskUsedUsdE8 + a.riskDebitUsdE8 > s.riskLimitUsdE8) revert SessionRiskLimit();
        uint256 day = block.timestamp / 1 days;
        if (globalDailyRiskUsedUsdE8[day] + a.riskDebitUsdE8 > proofPolicy.globalDailyRiskUsdE8) revert GlobalRiskLimit();
        if (dailySpentUsdE8[day] + spendDebit > maxDailySpendUsdE8) revert DailySpendLimit();
        if (a.tokenIn == usdc && dailySpentUsdc[day] + a.amount > maxSpendPerDay) revert DailySpendLimit();
        _beforeOperation(a);
        uint256[4] memory before_ = balances();
        if (keccak256(abi.encode(before_)) != keccak256(abi.encode(phi.beforeBalances))) revert StateDrift();
        uint256 receiptBefore;
        bytes32 payeeDay;
        if (a.kind == 2) {
            receiptBefore = a.tokenIn == address(0) ? a.recipient.balance : IERC20(a.tokenIn).balanceOf(a.recipient);
            payeeDay = keccak256(abi.encode(day, a.tokenIn, a.recipient));
            if (payeeDailySpent[payeeDay] + a.amount > payees[a.tokenIn][a.recipient].perDay) revert DailySpendLimit();
            payeeDailySpent[payeeDay] += a.amount;
        }
        usedNonce[a.nonce] = true; auth.actions++; auth.spendUsedUsdE8 += spendDebit;
        s.riskUsedUsdE8 += a.riskDebitUsdE8; globalDailyRiskUsedUsdE8[day] += a.riskDebitUsdE8;
        dailySpentUsdE8[day] += spendDebit;
        if (a.tokenIn == usdc) dailySpentUsdc[day] += a.amount;
        if (a.rebalance) auth.lastRebalance = block.timestamp;
        if (a.kind == 1) {
            IERC20(a.tokenIn).forceApprove(a.target, a.amount);
            ISwapAdapter(a.target).exactInput(a.tokenIn, a.tokenOut, a.amount, a.minOutput, address(this));
            IERC20(a.tokenIn).forceApprove(a.target, 0);
        } else if (a.kind == 2) {
            if (a.tokenIn == address(0)) { (bool ok,) = a.recipient.call{value:a.amount}(""); if (!ok) revert ReceiptNotMet(); }
            else IERC20(a.tokenIn).safeTransfer(a.recipient, a.amount);
        } else if (a.kind == 3) {
            IERC20(usdc).forceApprove(a.target, a.amount);
            approvedVault.deposit(a.amount, address(this)); IERC20(usdc).forceApprove(a.target, 0);
        } else approvedVault.redeem(a.amount, address(this), address(this));
        uint256[4] memory after_ = balances(); int256[4] memory deltas;
        for (uint256 i; i < 4; ++i) {
            deltas[i] = _delta(before_[i], after_[i]);
            if (deltas[i] < phi.minDeltas[i]) revert PostConditionFailed();
        }
        uint256 index = a.tokenIn == usdc ? 0 : a.tokenIn == wavax ? 1 : a.tokenIn == address(approvedVault) ? 2 : 3;
        if (deltas[index] != -int256(a.amount)) revert UnexpectedTransfer();
        if (after_[1] > phi.maxWavaxBalance) revert PostConditionFailed();
        _checkAllowances();
        uint256 received;
        if (a.kind == 2) {
            uint256 receiptAfter = a.tokenIn == address(0) ? a.recipient.balance : IERC20(a.tokenIn).balanceOf(a.recipient);
            if (receiptAfter < receiptBefore || receiptAfter - receiptBefore < phi.receiptCredit) revert ReceiptNotMet();
            received = receiptAfter - receiptBefore;
        }
        _checkCodeAndRate();
        emit OperationExecuted(a.nonce, a.sessionId, a.kind, a.evidenceRoot, a.proofContextHash, deltas, received);
    }
    function _beforeOperation(Operation calldata) internal virtual {}
    function _spendDebit(Operation calldata a) internal pure virtual returns(uint256) { return a.spendDebitUsdE8; }
    function _maxOperationDebit(Operation calldata) internal view virtual returns(uint256) { return maxOperationUsdE8; }
    function _checkAllowances() internal view virtual {
        if (IERC20(usdc).allowance(address(this), proofAdapter) != 0 || IERC20(wavax).allowance(address(this), proofAdapter) != 0
            || IERC20(usdc).allowance(address(this), address(approvedVault)) != 0
            || approvedVault.allowance(address(this), proofAdapter) != 0) revert PostConditionFailed();
    }
}
