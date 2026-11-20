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
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";

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
    // V2 activation is permanent: legacy signatures can never bypass proof enforcement.
    bool public v2Enabled;
    address public proofAdapter;
    bytes32 public v2ConfigHash;
    struct ProofPolicy {
        uint256 maxWavaxPerSwap;
        uint256 maxRelativeLossBps;
        uint256 fixedLossUsdE8;
        uint256 oracleBandBps;
        uint256 toleranceBps;
        uint256 maxOracleAge;
        uint256 maxSessionRiskUsdE8;
        uint256 globalDailyRiskUsdE8;
        bytes32 oracleSourceHash;
        bool ownerApproved;
    }
    ProofPolicy public proofPolicy;
    struct Session {
        bytes32 policyHash;
        uint256 startsAt;
        uint256 expiresAt;
        uint256 riskLimitUsdE8;
        uint256 riskUsedUsdE8;
        bool active;
    }
    mapping(bytes32 => Session) public sessions;
    mapping(uint256 => uint256) public globalDailyRiskUsedUsdE8;
    struct BalanceBound { address asset; int256 minDelta; }
    struct AllowanceCap { address token; address spender; uint256 maxRemaining; }
    struct PostConditionsV2 { BalanceBound[] balanceBounds; AllowanceCap[] allowanceCaps; }
    struct ApprovalV2 {
        bytes32 intentHash;
        bytes32 calldataHash;
        bytes32 policyHash;
        bytes32 evidenceRoot;
        bytes32 proofContextHash;
        bytes32 postConditionsHash;
        bytes32 sessionId;
        uint256 riskDebitUsdE8;
        uint256 nonce;
        uint256 deadline;
        address adapter;
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint256 minAmountOut;
    }
    bytes32 public constant APPROVAL_V2_TYPEHASH = keccak256("ApprovalV2(bytes32 intentHash,bytes32 calldataHash,bytes32 policyHash,bytes32 evidenceRoot,bytes32 proofContextHash,bytes32 postConditionsHash,bytes32 sessionId,uint256 riskDebitUsdE8,uint256 nonce,uint256 deadline,address adapter,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut)");
    error ProofRequired();
    error InvalidPostConditions();
    error PostConditionFailed();
    error SessionUnavailable();
    error SessionRiskLimit();
    error GlobalRiskLimit();
    event ProofPolicyUpdated(bytes32 indexed configHash, address adapter);
    event SessionCreated(bytes32 indexed sessionId, bytes32 indexed policyHash, uint256 limit, uint256 startsAt, uint256 expiresAt);
    event SessionRevoked(bytes32 indexed sessionId);
    event ProofCommitted(uint256 indexed nonce, bytes32 indexed sessionId, bytes32 indexed proofContextHash,
        bytes32 postConditionsHash, uint256 riskDebitUsdE8, int256 usdcDelta, int256 wavaxDelta);
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


    // Separate transfer domain and policy. Transfers are disabled until the owner configures a recipient.
    struct TransferRecipient {
        uint256 perTransfer;
        uint256 perDay;
        uint256 expiresAt;
        uint256 priceUsdE8;
        uint8 decimals;
        bool active;
    }
    struct TransferApprovalV2 {
        bytes32 intentHash;
        bytes32 taskHash;
        bytes32 policyHash;
        bytes32 evidenceRoot;
        bytes32 proofContextHash;
        bytes32 sessionId;
        uint256 transferPolicyVersion;
        uint256 taskBudget;
        uint256 riskDebitUsdE8;
        uint256 nonce;
        uint256 deadline;
        address token;
        address recipient;
        uint256 amount;
    }
    bytes32 public constant TRANSFER_TYPEHASH = keccak256("TransferApprovalV2(bytes32 intentHash,bytes32 taskHash,bytes32 policyHash,bytes32 evidenceRoot,bytes32 proofContextHash,bytes32 sessionId,uint256 transferPolicyVersion,uint256 taskBudget,uint256 riskDebitUsdE8,uint256 nonce,uint256 deadline,address token,address recipient,uint256 amount)");
    uint256 public transferPolicyVersion;
    mapping(address => mapping(address => TransferRecipient)) public transferRecipients;
    mapping(bytes32 => uint256) public transferDailySpent;
    mapping(bytes32 => uint256) public transferTaskSpent;
    mapping(bytes32 => uint256) public transferTaskBudgets;
    event TransferRecipientUpdated(address indexed token, address indexed recipient, uint256 version);
    event ApprovedTransferExecuted(uint256 indexed nonce, bytes32 indexed intentHash, bytes32 indexed taskHash,
        address token, address recipient, uint256 amount, bytes32 evidenceRoot);

    function configureTransferRecipient(address token, address recipient, TransferRecipient calldata rule) external onlyOwner {
        if ((token != usdc && token != wavax) || recipient == address(0) || recipient == address(this)
            || recipient == usdc || recipient == wavax || recipient == proofAdapter
            || recipient == attestor || (rule.active && (rule.perTransfer == 0
            || rule.perDay < rule.perTransfer || rule.expiresAt <= block.timestamp
            || rule.priceUsdE8 == 0 || rule.decimals > 18
            || IERC20Metadata(token).decimals() != rule.decimals))) revert InvalidConfiguration();
        transferRecipients[token][recipient] = rule;
        emit TransferRecipientUpdated(token, recipient, ++transferPolicyVersion);
    }
    function hashTransferApprovalV2(TransferApprovalV2 calldata a) public view returns (bytes32) {
        bytes32 domain = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256("TreasuryPolicyVault"), keccak256("transfer-2"), block.chainid, address(this)));
        return keccak256(abi.encodePacked(hex"1901", domain, keccak256(abi.encode(TRANSFER_TYPEHASH, a))));
    }
    function executeApprovedTransferV2(TransferApprovalV2 calldata a, bytes calldata signature)
        external nonReentrant whenNotPaused
    {
        if (!v2Enabled) revert ProofRequired();
        if (!policyActive || a.policyHash != activePolicyHash || block.timestamp > policyExpiresAt) revert PolicyRevoked();
        if (a.deadline < block.timestamp || a.deadline > block.timestamp + maxApprovalTtl
            || a.deadline > policyExpiresAt) revert ExpiredApproval();
        if (usedNonce[a.nonce]) revert NonceReplay();
        if (ECDSA.recover(hashTransferApprovalV2(a), signature) != attestor) revert BadSignature();
        if (a.intentHash == bytes32(0) || a.taskHash == bytes32(0) || a.evidenceRoot == bytes32(0)
            || a.proofContextHash == bytes32(0) || a.transferPolicyVersion != transferPolicyVersion) revert HashMismatch();
        TransferRecipient storage rule = transferRecipients[a.token][a.recipient];
        if (!rule.active || block.timestamp > rule.expiresAt || a.deadline > rule.expiresAt
            || !allowedTokens[a.token] || (a.token != usdc && a.token != wavax)
            || a.recipient == address(this) || a.recipient == proofAdapter || a.recipient == attestor
            || a.amount == 0 || a.amount > rule.perTransfer
            || IERC20Metadata(a.token).decimals() != rule.decimals) revert InvalidCall();
        // Owner-configured LOCAL reference valuation, rounded up. Missing valuation cannot authorize outflow.
        uint256 valueUsdE8 = (a.amount * rule.priceUsdE8 + 10**rule.decimals - 1) / 10**rule.decimals;
        if (a.riskDebitUsdE8 < valueUsdE8) revert InvalidPostConditions();
        Session storage session = sessions[a.sessionId];
        if (!session.active || session.policyHash != activePolicyHash || block.timestamp < session.startsAt
            || block.timestamp > session.expiresAt || a.deadline > session.expiresAt) revert SessionUnavailable();
        if (session.riskUsedUsdE8 + a.riskDebitUsdE8 > session.riskLimitUsdE8) revert SessionRiskLimit();
        uint256 day = block.timestamp / 1 days;
        if (globalDailyRiskUsedUsdE8[day] + a.riskDebitUsdE8 > proofPolicy.globalDailyRiskUsdE8) revert GlobalRiskLimit();
        bytes32 daily = keccak256(abi.encode(a.token, a.recipient, day));
        if (transferDailySpent[daily] + a.amount > rule.perDay) revert DailySpendLimit();
        // Task identity also binds token/recipient and budget, preventing scope substitution.
        bytes32 task = keccak256(abi.encode(a.taskHash, a.token, a.recipient));
        uint256 budget = transferTaskBudgets[task];
        if (a.taskBudget == 0 || (budget != 0 && budget != a.taskBudget)
            || transferTaskSpent[task] + a.amount > a.taskBudget) revert DailySpendLimit();
        if (a.token == usdc && dailySpentUsdc[day] + a.amount > maxSpendPerDay) revert DailySpendLimit();
        uint256 beforeVault = IERC20(a.token).balanceOf(address(this));
        uint256 beforeRecipient = IERC20(a.token).balanceOf(a.recipient);
        address other = a.token == usdc ? wavax : usdc;
        uint256 beforeOther = IERC20(other).balanceOf(address(this));
        usedNonce[a.nonce] = true;
        transferTaskBudgets[task] = a.taskBudget;
        transferTaskSpent[task] += a.amount;
        transferDailySpent[daily] += a.amount;
        if (a.token == usdc) dailySpentUsdc[day] += a.amount;
        session.riskUsedUsdE8 += a.riskDebitUsdE8;
        globalDailyRiskUsedUsdE8[day] += a.riskDebitUsdE8;
        IERC20(a.token).safeTransfer(a.recipient, a.amount);
        if (beforeVault < a.amount || IERC20(a.token).balanceOf(address(this)) != beforeVault - a.amount
            || IERC20(a.token).balanceOf(a.recipient) != beforeRecipient + a.amount
            || IERC20(other).balanceOf(address(this)) != beforeOther) revert PostConditionFailed();
        emit ApprovedTransferExecuted(a.nonce, a.intentHash, a.taskHash, a.token, a.recipient, a.amount, a.evidenceRoot);
    }

    constructor(address admin, address signer, address input, address output)
        Ownable(admin) EIP712("TreasuryPolicyVault", "1")
    {
        if (signer == address(0) || signer == admin || input == output || input.code.length == 0 || output.code.length == 0)
            revert InvalidConfiguration();
        usdc = input; wavax = output; attestor = signer;
        allowedTokens[input] = true; allowedTokens[output] = true;
    }
    function _invalidate() internal { policyActive = false; emit PolicyUpdated(activePolicyHash, ++policyVersion); }
    /// @notice Owner-reviewed RPC/simulation window. Changing it revokes existing policy/signatures.
    function setApprovalTtl(uint256 seconds_) external onlyOwner {
        if (seconds_ == 0 || seconds_ > 300) revert InvalidConfiguration();
        maxApprovalTtl = seconds_;
        _invalidate();
    }
    function configurePolicy(bytes32 commitment, uint256 perSwap, uint256 perDay, uint256 slippageBps, uint256 expiresAt)
        external onlyOwner
    {
        // Never reactivate a previous hash: signatures from older configurations must stay invalid.
        if (commitment == bytes32(0) || perSwap == 0 || perDay < perSwap || slippageBps > 10000 || expiresAt <= block.timestamp)
            revert InvalidConfiguration();
        ++policyVersion;
        if (v2Enabled) commitment = keccak256(abi.encode(commitment, v2ConfigHash, proofAdapter, trackedRegistryHash()));
        activePolicyHash = keccak256(abi.encode(commitment, policyVersion, address(this), block.chainid,
            attestor, perSwap, perDay, slippageBps, expiresAt, maxApprovalTtl));
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
        if (v2Enabled) revert ProofRequired();
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

    function configureProofPolicy(address adapter, ProofPolicy calldata p) external onlyOwner {
        if (!allowedRouters[adapter] || adapter.code.length == 0
            || p.maxRelativeLossBps >= 10000 || p.oracleBandBps >= 10000 || p.toleranceBps >= 10000
            || p.maxOracleAge == 0 || p.maxOracleAge > 3600 || p.oracleSourceHash == bytes32(0)
            || p.maxSessionRiskUsdE8 == 0 || p.globalDailyRiskUsdE8 == 0
            || (block.chainid == 43113 && !p.ownerApproved)
            || IERC20Metadata(usdc).decimals() != 6 || IERC20Metadata(wavax).decimals() != 18)
            revert InvalidConfiguration();
        v2Enabled = true;
        proofAdapter = adapter;
        proofPolicy = p;
        v2ConfigHash = keccak256(abi.encode(p));
        _invalidate();
        emit ProofPolicyUpdated(v2ConfigHash, adapter);
    }

    function trackedRegistryHash() public view returns (bytes32) {
        address[] memory assets = new address[](2);
        assets[0] = usdc < wavax ? usdc : wavax;
        assets[1] = usdc < wavax ? wavax : usdc;
        // ABI matches Registry: uint256 version + (address,uint8)[] assets.
        AssetSpec[] memory specs = new AssetSpec[](2);
        for (uint256 i; i < 2; ++i) specs[i] = AssetSpec(assets[i], assets[i] == usdc ? 6 : 18);
        return keccak256(abi.encode(uint256(1), specs));
    }
    struct AssetSpec { address asset; uint8 decimals; }

    function createSession(bytes32 id, uint256 startsAt, uint256 expiresAt, uint256 riskLimit) external onlyOwner {
        if (!v2Enabled || !policyActive || block.timestamp > policyExpiresAt || id == bytes32(0)
            || sessions[id].policyHash != bytes32(0) || startsAt > expiresAt
            || expiresAt <= block.timestamp || expiresAt > policyExpiresAt
            || riskLimit == 0 || riskLimit > proofPolicy.maxSessionRiskUsdE8) revert InvalidConfiguration();
        sessions[id] = Session(activePolicyHash, startsAt, expiresAt, riskLimit, 0, true);
        emit SessionCreated(id, activePolicyHash, riskLimit, startsAt, expiresAt);
    }
    function revokeSession(bytes32 id) external onlyOwner {
        if (sessions[id].policyHash == bytes32(0)) revert SessionUnavailable();
        sessions[id].active = false;
        emit SessionRevoked(id);
    }
    function hashPostConditions(PostConditionsV2 calldata phi) public pure returns (bytes32) {
        return keccak256(abi.encode(phi));
    }
    function hashApprovalV2(ApprovalV2 calldata a) public view returns (bytes32) {
        // Separate EIP-712 version; keep the historical V1 domain for existing deployments/tests.
        bytes32 domain = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256("TreasuryPolicyVault"), keccak256("2"), block.chainid, address(this)));
        return keccak256(abi.encodePacked(hex"1901", domain, keccak256(abi.encode(APPROVAL_V2_TYPEHASH, a))));
    }
    function _delta(uint256 beforeBal, uint256 afterBal) internal pure returns (int256) {
        uint256 magnitude = afterBal >= beforeBal ? afterBal - beforeBal : beforeBal - afterBal;
        if (magnitude > uint256(type(int256).max)) revert PostConditionFailed();
        return afterBal >= beforeBal ? int256(magnitude) : -int256(magnitude);
    }
    function executeApprovedSwapV2(ApprovalV2 calldata a, bytes calldata data,
        PostConditionsV2 calldata phi, bytes calldata signature) external nonReentrant whenNotPaused
    {
        if (!v2Enabled) revert ProofRequired();
        if (!policyActive || a.policyHash != activePolicyHash || block.timestamp > policyExpiresAt) revert PolicyRevoked();
        if (a.deadline < block.timestamp || a.deadline > block.timestamp + maxApprovalTtl
            || a.deadline > policyExpiresAt) revert ExpiredApproval();
        if (usedNonce[a.nonce]) revert NonceReplay();
        if (attestor == address(0) || ECDSA.recover(hashApprovalV2(a), signature) != attestor) revert BadSignature();
        if (a.intentHash == bytes32(0) || a.evidenceRoot == bytes32(0) || a.proofContextHash == bytes32(0)
            || keccak256(data) != a.calldataHash || hashPostConditions(phi) != a.postConditionsHash) revert HashMismatch();
        if (a.adapter != proofAdapter || !allowedRouters[a.adapter] || !allowedTokens[a.tokenIn]
            || !allowedTokens[a.tokenOut] || a.tokenIn == a.tokenOut
            || (a.tokenIn != usdc && a.tokenIn != wavax) || (a.tokenOut != usdc && a.tokenOut != wavax)
            || data.length != 164 || bytes4(data[:4]) != ISwapAdapter.exactInput.selector) revert InvalidCall();
        (address input, address output, uint256 amount, uint256 minOut, address recipient) =
            abi.decode(data[4:], (address, address, uint256, uint256, address));
        if (input != a.tokenIn || output != a.tokenOut || amount != a.amountIn || minOut != a.minAmountOut
            || recipient != address(this) || minOut == 0 || amount == 0 || amount > uint256(type(int256).max)
            || minOut > uint256(type(int256).max) || keccak256(data) != keccak256(abi.encodeCall(
                ISwapAdapter.exactInput, (input, output, amount, minOut, recipient)))) revert InvalidCall();
        if (amount > (input == usdc ? maxPerSwap : proofPolicy.maxWavaxPerSwap)) revert TradeSizeLimit();
        Session storage s = sessions[a.sessionId];
        if (!s.active || s.policyHash != activePolicyHash || block.timestamp < s.startsAt
            || block.timestamp > s.expiresAt || a.deadline > s.expiresAt) revert SessionUnavailable();
        if (s.riskUsedUsdE8 > s.riskLimitUsdE8 || a.riskDebitUsdE8 > s.riskLimitUsdE8 - s.riskUsedUsdE8) revert SessionRiskLimit();
        uint256 day = block.timestamp / 1 days;
        uint256 globalUsed = globalDailyRiskUsedUsdE8[day];
        if (globalUsed > proofPolicy.globalDailyRiskUsdE8 || a.riskDebitUsdE8 > proofPolicy.globalDailyRiskUsdE8 - globalUsed) revert GlobalRiskLimit();
        if (input == usdc && (dailySpentUsdc[day] > maxSpendPerDay || amount > maxSpendPerDay - dailySpentUsdc[day])) revert DailySpendLimit();
        if (phi.balanceBounds.length != 2 || phi.allowanceCaps.length != 2) revert InvalidPostConditions();
        address first = usdc < wavax ? usdc : wavax;
        address second = usdc < wavax ? wavax : usdc;
        uint256[2] memory beforeBalances;
        for (uint256 i; i < 2; ++i) {
            address asset = i == 0 ? first : second;
            BalanceBound calldata bound = phi.balanceBounds[i];
            AllowanceCap calldata cap = phi.allowanceCaps[i];
            if (bound.asset != asset || cap.token != asset || cap.spender != a.adapter || cap.maxRemaining != 0
                || (asset == input && bound.minDelta != -int256(amount))
                || (asset == output && bound.minDelta < int256(minOut))) revert InvalidPostConditions();
            beforeBalances[i] = IERC20(asset).balanceOf(address(this));
        }
        usedNonce[a.nonce] = true;
        if (input == usdc) dailySpentUsdc[day] += amount;
        s.riskUsedUsdE8 += a.riskDebitUsdE8;
        globalDailyRiskUsedUsdE8[day] += a.riskDebitUsdE8;
        IERC20(input).forceApprove(a.adapter, amount);
        ISwapAdapter(a.adapter).exactInput(input, output, amount, minOut, address(this));
        IERC20(input).forceApprove(a.adapter, 0);
        int256[2] memory deltas;
        for (uint256 i; i < 2; ++i) {
            address asset = i == 0 ? first : second;
            deltas[i] = _delta(beforeBalances[i], IERC20(asset).balanceOf(address(this)));
            if (deltas[i] < phi.balanceBounds[i].minDelta
                || IERC20(asset).allowance(address(this), a.adapter) != 0) revert PostConditionFailed();
            if (asset == input && deltas[i] != -int256(amount)) revert UnexpectedTransfer();
        }
        uint256 outputAmount = uint256(deltas[output == first ? 0 : 1]);
        emit SwapExecuted(a.nonce, a.policyHash, a.evidenceRoot, input, output, amount, outputAmount);
        emit ProofCommitted(a.nonce, a.sessionId, a.proofContextHash, a.postConditionsHash,
            a.riskDebitUsdE8, deltas[usdc == first ? 0 : 1], deltas[wavax == first ? 0 : 1]);
    }
}
