// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {PolicyVault} from "../src/PolicyVault.sol";
import {PolicyVaultV3} from "../src/PolicyVaultV3.sol";
import {PolicyVaultMVP} from "../src/PolicyVaultMVP.sol";
import {MockWAVAX} from "../src/mocks/MockWAVAX.sol";
import {MockSwapAdapter} from "../src/adapters/MockSwapAdapter.sol";
import {FeeUSDC,V3Vm} from "./PolicyVaultV3.t.sol";
import {Vm} from "./PolicyVault.t.sol";

contract PolicyVaultMVPTest {
    function testMergedLocalTransferCannotBypassMvp() public {
        PolicyVault.TransferRecipient memory rule;
        vm.expectRevert(PolicyVault.InvalidCall.selector);
        v.configureTransferRecipient(address(u),PAYEE,rule);
        PolicyVault.TransferApprovalV2 memory approval;
        vm.expectRevert(PolicyVault.InvalidCall.selector);
        v.executeApprovedTransferV2(approval,hex"");
        require(address(v).code.length <= 24576,"EIP170");
    }
    receive() external payable {}
    Vm constant vm=Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    uint256 constant LOCAL_SIGNER=0x5633;
    address constant PAYEE=address(0xA11CE);
    bytes32 constant SESSION=keccak256("MVP_LOCAL_SESSION");
    FeeUSDC u;MockWAVAX w;MockSwapAdapter adapter;PolicyVaultMVP v;
    function setUp() public {
        vm.warp(1800000000);vm.chainId(31337);
        u=new FeeUSDC(address(this));w=new MockWAVAX(address(this));
        adapter=new MockSwapAdapter(address(this),address(u),address(w));
        v=new PolicyVaultMVP(address(this),vm.addr(LOCAL_SIGNER),address(u),address(w));
        v.setRouter(address(adapter),true);
        v.configureProofPolicy(address(adapter),PolicyVault.ProofPolicy(10e18,300,0,100,40,180,100e8,200e8,keccak256("LOCAL_REFERENCE"),false));
        v.configureMVP(200e8,1000e8,25e6,75e6,2500);
        v.setMvpPayee(PAYEE,25e6,50e6,100e6);
        policy();session(SESSION,500e8,50e6,10);
        u.mint(address(v),1000e6);w.mint(address(adapter),10000e18);u.mint(address(adapter),100000e6);
    }
    function policy() internal {v.configurePolicy(keccak256("MVP_OWNER_POLICY"),200e6,1000e6,100,block.timestamp+1 days);}
    function session(bytes32 id,uint256 swaps,uint256 payments,uint256 actions) internal {
        v.createSession(id,block.timestamp,block.timestamp+3600,100e8);v.authorizeMvpSession(id,19,swaps,payments,actions,60);
    }
    function bind(PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi) internal view returns(PolicyVaultV3.Operation memory) {
        a.constraintsHash=keccak256(abi.encode(phi));(address t,uint256 value,bytes memory data)=v.operationCall(a);
        a.calldataHash=keccak256(abi.encode(t,value,data));return a;
    }
    function make(uint8 kind,uint256 amount,uint256 nonce) internal view returns(PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi) {
        a.kind=kind;a.policyHash=v.activePolicyHash();a.sessionId=SESSION;a.intentHash=keccak256("MVP_EXACT_INTENT");
        a.evidenceRoot=keccak256("LOCAL_EVM");a.proofContextHash=keccak256("CERTIFIED_LOCAL_PHI");
        a.target=kind==1?address(adapter):address(u);a.tokenIn=address(u);a.tokenOut=kind==1?address(w):address(u);
        a.recipient=kind==1?address(v):PAYEE;a.amount=amount;a.minOutput=kind==1?amount*5e10*9900/10000:amount;
        a.spendDebitUsdE8=amount*100;a.riskDebitUsdE8=kind==1?1e8:0;a.nonce=nonce;a.deadline=block.timestamp+30;
        phi.beforeBalances=v.balances();phi.minDeltas[0]=-int256(amount);phi.maxWavaxBalance=15e18;
        if(kind==1)phi.minDeltas[1]=int256(a.minOutput);else phi.receiptCredit=amount;
        a=bind(a,phi);
    }
    function sign(PolicyVaultV3.Operation memory a) internal returns(bytes memory) {
        (uint8 vv,bytes32 r,bytes32 s)=vm.sign(LOCAL_SIGNER,v.hashOperation(a));return abi.encodePacked(r,s,vv);
    }
    function run(uint8 kind,uint256 amount,uint256 nonce) internal {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(kind,amount,nonce);v.executeOperation(a,phi,sign(a));
    }
    function failure(PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi,bytes4 reason) internal {
        bytes memory signature=sign(a);vm.expectRevert(reason);v.executeOperation(a,phi,signature);require(!v.usedNonce(a.nonce));
    }
    function testSwapBothDirectionsAndPayment() public {
        run(1,100e6,1);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,1e18,2);
        a.tokenIn=address(w);a.tokenOut=address(u);a.minOutput=19e6;a.spendDebitUsdE8=21e8;
        phi.minDeltas[0]=19e6;phi.minDeltas[1]=-1e18;a=bind(a,phi);v.executeOperation(a,phi,sign(a));
        run(2,1e6,3);require(u.balanceOf(PAYEE)==1e6);
        (,,,uint256 paymentUsed)=v.spendScopes(SESSION);require(paymentUsed==1e6);
    }
    function testAttackInvalidPayee() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);
        a.recipient=address(0xBAD);a=bind(a,phi);failure(a,phi,PolicyVaultV3.PayeeNotAllowed.selector);
    }
    function testAttackUnauthorizedProposal() public {testAttackInvalidPayee();}
    function testAttackTamperedCall() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);
        a.calldataHash=keccak256("arbitrary approval");failure(a,phi,PolicyVault.HashMismatch.selector);
    }
    function testAttackStateDrift() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,100e6,1);
        phi.minDeltas[1]=int256(5e18*9960/10000);a=bind(a,phi);adapter.setOutputPerUsdc(5e16*9950/10000);
        failure(a,phi,PolicyVault.PostConditionFailed.selector);require(u.balanceOf(address(v))==1000e6);
        require(v.dailySwapSpentUsdE8(block.timestamp/1 days)==0);
    }
    function testAttackSevereSlippage() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,100e6,1);
        bytes memory signature=sign(a);adapter.setOutputPerUsdc(1e16);
        vm.expectRevert(MockSwapAdapter.MinOutputNotMet.selector);v.executeOperation(a,phi,signature);
    }
    function testAttackCumulativeLoss() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,10e6,1);
        a.riskDebitUsdE8=100e8;v.executeOperation(a,phi,sign(a));
        (a,phi)=make(1,10e6,2);failure(a,phi,PolicyVault.SessionRiskLimit.selector);
    }
    function testAttackExcessiveAllowance() public {
        vm.prank(address(v));w.approve(address(adapter),type(uint256).max);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);
        failure(a,phi,PolicyVault.PostConditionFailed.selector);
    }
    function testAttackKillSwitch() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);bytes memory signature=sign(a);
        v.pause();vm.expectRevert();v.executeOperation(a,phi,signature);v.unpause();v.revokeSession(SESSION);
        failure(a,phi,PolicyVault.SessionUnavailable.selector);
    }
    function testAttackDailyCap() public {
        run(2,25e6,1);run(2,25e6,2);
        bytes32 other=keccak256("OTHER");session(other,500e8,50e6,10);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,25e6,3);
        a.sessionId=other;v.executeOperation(a,phi,sign(a));
        (a,phi)=make(2,1e6,4);a.sessionId=other;failure(a,phi,PolicyVault.DailySpendLimit.selector);
    }
    function testPaymentSessionAndRecipientCapsIndependentOfRisk() public {
        run(2,25e6,1);run(2,25e6,2);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1,3);
        failure(a,phi,PolicyVaultV3.ScopeViolation.selector);(,,,,uint256 risk,)=v.sessions(SESSION);require(risk==0);
    }
    function testFeeTokenAndRecipientRedirectionFailClosed() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);
        u.attack(5000,false);failure(a,phi,PolicyVaultV3.ReceiptNotMet.selector);require(u.balanceOf(PAYEE)==0);
        u.attack(0,true);failure(a,phi,PolicyVaultV3.ReceiptNotMet.selector);
    }
    function testNoOvercreditAndNoReducedReceipt() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);
        phi.receiptCredit=a.amount+1;a=bind(a,phi);failure(a,phi,PolicyVaultMVP.UnsupportedOperation.selector);
        phi.receiptCredit=a.amount-1;a.minOutput=a.amount-1;a=bind(a,phi);failure(a,phi,PolicyVaultMVP.UnsupportedOperation.selector);
    }
    function testNativeAndWavaxPaymentsDisabled() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);
        a.tokenIn=address(0);a.tokenOut=address(0);a.target=PAYEE;a=bind(a,phi);failure(a,phi,PolicyVaultMVP.UnsupportedOperation.selector);
        a.tokenIn=address(w);a.tokenOut=address(w);a.target=address(w);a=bind(a,phi);failure(a,phi,PolicyVaultMVP.UnsupportedOperation.selector);
    }
    function testInvestmentVaultOperationsDisabled() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);
        a.kind=3;a=bind(a,phi);failure(a,phi,PolicyVaultMVP.UnsupportedOperation.selector);
        a.kind=4;a=bind(a,phi);failure(a,phi,PolicyVaultMVP.UnsupportedOperation.selector);
        vm.expectRevert(PolicyVaultMVP.UnsupportedOperation.selector);v.configureV3(address(0),0,0,0,0,0,0,0);
    }
    function testWrongSignerAndChainDomain() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);
        (uint8 vv,bytes32 r,bytes32 s)=vm.sign(0xBADE,v.hashOperation(a));
        vm.expectRevert(PolicyVault.BadSignature.selector);v.executeOperation(a,phi,abi.encodePacked(r,s,vv));
        bytes memory signature=sign(a);vm.chainId(43113);
        vm.expectRevert(PolicyVault.BadSignature.selector);v.executeOperation(a,phi,signature);
    }
    function testReplayExpiryAndPolicyRotation() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);bytes memory signature=sign(a);
        v.executeOperation(a,phi,signature);vm.expectRevert(PolicyVault.NonceReplay.selector);v.executeOperation(a,phi,signature);
        (a,phi)=make(2,1e6,2);signature=sign(a);vm.warp(block.timestamp+31);
        vm.expectRevert(PolicyVault.ExpiredApproval.selector);v.executeOperation(a,phi,signature);
        (a,phi)=make(2,1e6,3);signature=sign(a);policy();
        vm.expectRevert(PolicyVault.PolicyRevoked.selector);v.executeOperation(a,phi,signature);
    }
    function testSessionExpiryAndOperationScope() public {
        bytes32 short=keccak256("short");v.createSession(short,block.timestamp,block.timestamp+1,10e8);v.authorizeMvpSession(short,1,100e8,0,2,0);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);a.sessionId=short;a.deadline=block.timestamp+1;
        failure(a,phi,PolicyVaultV3.ScopeViolation.selector);
        vm.warp(block.timestamp+2);(a,phi)=make(1,1e6,2);a.sessionId=short;
        failure(a,phi,PolicyVault.SessionUnavailable.selector);
    }
    function testOwnerAdministrationCannotBeUsedByAttestorOrRelayer() public {
        vm.prank(vm.addr(LOCAL_SIGNER));vm.expectRevert();v.pause();
        vm.prank(address(0xBEEF));vm.expectRevert();v.setMvpPayee(address(0xBAD),1e6,1e6,1e6);
        vm.prank(vm.addr(LOCAL_SIGNER));vm.expectRevert();v.authorizeMvpSession(SESSION,19,500e8,50e6,10,0);
        vm.expectRevert(PolicyVault.InvalidConfiguration.selector);v.authorizeMvpSession(SESSION,31,500e8,50e6,10,0);
    }
    function testLegacyGuardBypassIsDisabled() public {
        PolicyVault.Approval memory a;vm.expectRevert(PolicyVault.ProofRequired.selector);v.executeApprovedSwap(a,"","");
        PolicyVault.ApprovalV2 memory a2;PolicyVault.PostConditionsV2 memory phi;
        vm.expectRevert(PolicyVault.ProofRequired.selector);v.executeApprovedSwapV2(a2,"",phi,"");
    }
    function testFuzzPaymentExactReceipt(uint96 raw) public {
        uint256 value=uint256(raw)%25e6+1;run(2,value,1);require(u.balanceOf(PAYEE)==value);
    }
    function testPaymentOnlySessionDoesNotSpendSwapBudget() public {
        bytes32 id=keccak256("PAYMENT_ONLY");v.createSession(id,block.timestamp,block.timestamp+3600,1e8);
        v.authorizeMvpSession(id,2,0,1e6,1,0);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,1);
        a.sessionId=id;a.spendDebitUsdE8=101000000;v.executeOperation(a,phi,sign(a));
        (uint256 swapLimit,uint256 usedSwap,uint256 paymentLimit,uint256 paid)=v.spendScopes(id);
        require(swapLimit==0 && usedSwap==0 && paymentLimit==1e6 && paid==1e6);
    }
    function testOwnerMigrationFromPausedLegacyVault() public {
        PolicyVault old=new PolicyVault(address(this),vm.addr(LOCAL_SIGNER),address(u),address(w));
        u.mint(address(old),5e6);
        vm.expectRevert();old.withdraw(address(u),address(v),5e6);
        vm.prank(vm.addr(LOCAL_SIGNER));vm.expectRevert();old.pause();
        old.pause();old.withdraw(address(u),address(v),5e6);
        require(u.balanceOf(address(old))==0 && u.balanceOf(address(v))==1005e6 && !old.policyActive());
    }
    function testNativeRecoveryRequiresOwnerAndPause() public {
        V3Vm(address(vm)).deal(address(v),1e15);
        vm.prank(vm.addr(LOCAL_SIGNER));vm.expectRevert();v.recoverNative(1e15);
        vm.expectRevert();v.recoverNative(1e15);
        v.pause();uint256 before_=address(this).balance;v.recoverNative(1e15);
        require(address(v).balance==0 && address(this).balance==before_+1e15 && !v.policyActive());
    }
}
