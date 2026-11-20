// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {PolicyVaultV3} from "./PolicyVaultV3.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// @notice Single-tenant MVP. Exactly SWAP_EXACT_IN and USDC_PAYMENT.
/// Reuses the PACE/PGS execution guard; permanently excludes investment vaults and native/token payments.
contract PolicyVaultMVP is PolicyVaultV3 {
    struct SpendScope { uint256 swapLimitUsdE8; uint256 swapUsedUsdE8; uint256 paymentLimitUsdc; uint256 paymentUsedUsdc; }
    mapping(bytes32 => SpendScope) public spendScopes;
    mapping(address => uint256) public recipientSessionCaps;
    mapping(bytes32 => uint256) public sessionRecipientSpent;
    mapping(uint256 => uint256) public dailySwapSpentUsdE8;
    mapping(uint256 => uint256) public dailyPaymentSpentUsdc;
    uint256 public maxDailySwapUsdE8;
    uint256 public maxDailyPaymentUsdc;
    uint256 public maxPaymentUsdc;
    error UnsupportedOperation();
    event MvpConfigured(uint256 maxSwapUsdE8,uint256 dailySwapUsdE8,uint256 paymentCapUsdc,uint256 dailyPaymentUsdc);
    event MvpPayeeConfigured(address indexed recipient,uint256 perPayment,uint256 perSession,uint256 perDay);
    event MvpSessionAuthorized(bytes32 indexed sessionId,uint256 mask,uint256 swapLimitUsdE8,uint256 paymentLimitUsdc);

    constructor(address admin,address signer,address input,address output) PolicyVaultV3(admin,signer,input,output) {}

    /// @notice Administrative recovery only; unavailable to agent execution and only sends to Owner.
    function recoverNative(uint256 amount) external onlyOwner whenPaused nonReentrant {
        _invalidate();(bool ok,)=owner().call{value:amount}("");if(!ok) revert UnexpectedTransfer();
    }

    function configureMVP(uint256 maxSwapUsdE8,uint256 dailySwapUsdE8,uint256 paymentCapUsdc,
        uint256 dailyPaymentUsdc,uint256 exposureBps) external onlyOwner {
        if (!v2Enabled || proofAdapter.code.length==0 || maxSwapUsdE8==0 || dailySwapUsdE8<maxSwapUsdE8
            || paymentCapUsdc==0 || dailyPaymentUsdc<paymentCapUsdc || exposureBps>10000) revert InvalidConfiguration();
        adapterCodeHash=proofAdapter.codehash;usdcCodeHash=usdc.codehash;wavaxCodeHash=wavax.codehash;
        maxOperationUsdE8=maxSwapUsdE8;
        maxDailySwapUsdE8=dailySwapUsdE8;maxPaymentUsdc=paymentCapUsdc;maxDailyPaymentUsdc=dailyPaymentUsdc;
        maxDailySpendUsdE8=dailySwapUsdE8;
        maxWavaxExposureBps=exposureBps;_invalidate();
        emit MvpConfigured(maxSwapUsdE8,dailySwapUsdE8,paymentCapUsdc,dailyPaymentUsdc);
    }
    function configureV3(address,uint256,uint256,uint256,uint256,uint256,uint256,uint256) external pure override {
        revert UnsupportedOperation();
    }
    function authorizeSession(bytes32,uint256,uint256,uint256,uint256) external pure override { revert UnsupportedOperation(); }
    function authorizeMvpSession(bytes32 id,uint256 mask,uint256 swapLimitUsdE8,uint256 paymentLimitUsdc,
        uint256 maxActions,uint256 cooldown) external onlyOwner {
        Session storage s=sessions[id];
        if (!s.active || s.policyHash!=activePolicyHash || mask==0 || (mask & ~uint256(19))!=0
            || (mask & 16)!=0 && (mask & 1)==0 || maxActions==0 || authorities[id].operationMask!=0
            || ((mask & 1)!=0 && swapLimitUsdE8==0) || ((mask & 2)!=0 && paymentLimitUsdc==0)) revert InvalidConfiguration();
        authorities[id]=Authority(mask,swapLimitUsdE8,0,maxActions,0,cooldown,0);
        spendScopes[id]=SpendScope(swapLimitUsdE8,0,paymentLimitUsdc,0);
        emit AuthorityConfigured(id,mask,swapLimitUsdE8,maxActions,cooldown);
        emit MvpSessionAuthorized(id,mask,swapLimitUsdE8,paymentLimitUsdc);
    }
    function setPayee(address token,address recipient,uint256 perPayment,uint256 perDay) external override onlyOwner {
        if(token!=usdc) revert UnsupportedOperation();
        _setPayee(recipient,perPayment,perDay,perDay);
    }
    function setMvpPayee(address recipient,uint256 perPayment,uint256 perSession,uint256 perDay) external onlyOwner {
        _setPayee(recipient,perPayment,perSession,perDay);
    }
    function _setPayee(address recipient,uint256 perPayment,uint256 perSession,uint256 perDay) internal {
        if(recipient==address(0) || recipient==address(this) || recipient.code.length!=0
            || perSession<perPayment || perDay<perPayment) revert InvalidConfiguration();
        payees[usdc][recipient]=PayeeLimit(perPayment,perDay);recipientSessionCaps[recipient]=perSession;
        _invalidate();emit PayeeConfigured(usdc,recipient,perPayment,perDay);
        emit MvpPayeeConfigured(recipient,perPayment,perSession,perDay);
    }
    function _validateCall(Operation calldata a,Constraints calldata phi) internal view override {
        if(a.kind!=1 && a.kind!=2) revert UnsupportedOperation();
        if(a.kind==2 && (a.tokenIn!=usdc || a.tokenOut!=usdc || a.minOutput!=a.amount
            || phi.receiptCredit!=a.amount || a.amount>maxPaymentUsdc)) revert UnsupportedOperation();
        if(phi.minDeltas[2]!=0 || phi.minDeltas[3]!=0) revert InvalidPostConditions();
        super._validateCall(a,phi);
    }
    function _checkCodeAndRate() internal view override {
        if(proofAdapter.codehash!=adapterCodeHash || usdc.codehash!=usdcCodeHash || wavax.codehash!=wavaxCodeHash)
            revert CodeIdentityChanged();
    }
    function balances() public view override returns(uint256[4] memory b) {
        b[0]=IERC20(usdc).balanceOf(address(this));b[1]=IERC20(wavax).balanceOf(address(this));
        b[2]=0;b[3]=address(this).balance;
    }
    function _beforeOperation(Operation calldata a) internal override {
        SpendScope storage scope=spendScopes[a.sessionId];uint256 day=block.timestamp/1 days;
        if(a.kind==1) {
            if(a.spendDebitUsdE8>maxOperationUsdE8) revert TradeSizeLimit();
            if(scope.swapUsedUsdE8+a.spendDebitUsdE8>scope.swapLimitUsdE8) revert ScopeViolation();
            if(dailySwapSpentUsdE8[day]+a.spendDebitUsdE8>maxDailySwapUsdE8) revert DailySpendLimit();
            scope.swapUsedUsdE8+=a.spendDebitUsdE8;dailySwapSpentUsdE8[day]+=a.spendDebitUsdE8;
        } else {
            bytes32 key=keccak256(abi.encode(a.sessionId,a.recipient));
            if(scope.paymentUsedUsdc+a.amount>scope.paymentLimitUsdc
                || sessionRecipientSpent[key]+a.amount>recipientSessionCaps[a.recipient]) revert ScopeViolation();
            if(dailyPaymentSpentUsdc[day]+a.amount>maxDailyPaymentUsdc) revert DailySpendLimit();
            scope.paymentUsedUsdc+=a.amount;dailyPaymentSpentUsdc[day]+=a.amount;sessionRecipientSpent[key]+=a.amount;
        }
    }
    function _checkAllowances() internal view override {
        if(IERC20(usdc).allowance(address(this),proofAdapter)!=0 || IERC20(wavax).allowance(address(this),proofAdapter)!=0)
            revert PostConditionFailed();
    }
    function _spendDebit(Operation calldata a) internal pure override returns(uint256) { return a.kind==1?a.spendDebitUsdE8:0; }
    function _maxOperationDebit(Operation calldata a) internal view override returns(uint256) { return a.kind==1?maxOperationUsdE8:type(uint256).max; }
}
