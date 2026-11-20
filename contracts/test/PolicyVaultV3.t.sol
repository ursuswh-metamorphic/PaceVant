// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {PolicyVaultV3} from "../src/PolicyVaultV3.sol";
import {PolicyVault} from "../src/PolicyVault.sol";
import {MockUSDC} from "../src/mocks/MockUSDC.sol";
import {MockWAVAX} from "../src/mocks/MockWAVAX.sol";
import {DemoERC4626} from "../src/mocks/DemoERC4626.sol";
import {MockSwapAdapter} from "../src/adapters/MockSwapAdapter.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {Vm} from "./PolicyVault.t.sol";

interface V3Vm is Vm { function deal(address,uint256) external; }

contract FeeUSDC is MockUSDC {
    uint256 public feeBps;
    bool public redirect;
    address constant SINK = address(0xE711);
    constructor(address admin) MockUSDC(admin) {}
    function attack(uint256 fee, bool redirect_) external onlyOwner { feeBps=fee; redirect=redirect_; }
    function _update(address from,address to,uint256 value) internal override {
        if (from!=address(0) && to!=address(0)) {
            uint256 fee=value*feeBps/10000;
            super._update(from,redirect?SINK:to,value-fee);
            if(fee>0) super._update(from,SINK,fee);
        } else super._update(from,to,value);
    }
}

contract PolicyVaultV3Test {
    V3Vm constant vm=V3Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    // Deterministic LOCAL test signing only. Never a deployed account/key.
    uint256 constant TEST_SIGNER=0x5633;
    bytes32 constant SESSION=keccak256("LOCAL_V3_SESSION");
    address constant PAYEE=address(0xA11CE);
    FeeUSDC u; MockWAVAX w; MockSwapAdapter adapter; DemoERC4626 shares; PolicyVaultV3 v;

    function setUp() public {
        vm.warp(1800000000); vm.chainId(31337);
        u=new FeeUSDC(address(this));w=new MockWAVAX(address(this));
        adapter=new MockSwapAdapter(address(this),address(u),address(w));
        shares=new DemoERC4626(IERC20(address(u)));
        v=new PolicyVaultV3(address(this),vm.addr(TEST_SIGNER),address(u),address(w));
        v.setRouter(address(adapter),true);
        v.configureProofPolicy(address(adapter),PolicyVault.ProofPolicy(10e18,300,0,100,40,180,10e8,20e8,keccak256("LOCAL_REFERENCE"),false));
        v.configureV3(address(shares),990000,1010000,200e8,1000e8,200e6,1000e6,2500);
        v.setPayee(address(u),PAYEE,25e6,50e6);
        v.setPayee(address(0),PAYEE,1e17,2e17);
        configure(); v.createSession(SESSION,block.timestamp,block.timestamp+3600,6e8);
        v.authorizeSession(SESSION,31,500e8,10,60);
        u.mint(address(v),1000e6);w.mint(address(adapter),10000e18);u.mint(address(adapter),100000e6);
    }
    function configure() internal { v.configurePolicy(keccak256("OWNER_V3"),200e6,1000e6,100,block.timestamp+1 days); }
    function sign(PolicyVaultV3.Operation memory a) internal returns(bytes memory) {
        (uint8 vv,bytes32 r,bytes32 s)=vm.sign(TEST_SIGNER,v.hashOperation(a));return abi.encodePacked(r,s,vv);
    }
    function bind(PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi) internal view returns(PolicyVaultV3.Operation memory) {
        a.constraintsHash=keccak256(abi.encode(phi));
        (address target,uint256 value,bytes memory data)=v.operationCall(a);
        a.calldataHash=keccak256(abi.encode(target,value,data));return a;
    }
    function make(uint8 kind,uint256 amount,uint256 nonce) internal view returns(PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi) {
        a.kind=kind;a.policyHash=v.activePolicyHash();a.sessionId=SESSION;a.intentHash=keccak256("EXACT_INTENT");
        a.evidenceRoot=keccak256("LOCAL_EVM_EFFECTS");a.proofContextHash=keccak256("LOCAL_PROOF");
        a.amount=amount;a.nonce=nonce;a.deadline=block.timestamp+30;a.spendDebitUsdE8=amount*100;a.riskDebitUsdE8=1e8;
        a.tokenIn=address(u);a.recipient=address(v);a.target=address(adapter);a.tokenOut=address(w);
        phi.beforeBalances=v.balances();phi.minDeltas[0]=-int256(amount);phi.maxWavaxBalance=15e18;
        if(kind==1) { a.minOutput=adapter.quote(address(u),address(w),amount)*9900/10000;phi.minDeltas[1]=int256(a.minOutput); }
        if(kind==2) { a.target=address(u);a.tokenOut=address(u);a.recipient=PAYEE;a.minOutput=amount;phi.receiptCredit=amount; }
        if(kind==3) { a.target=address(shares);a.tokenOut=address(shares);a.minOutput=shares.previewDeposit(amount)*9960/10000;phi.minDeltas[2]=int256(a.minOutput); }
        if(kind==4) {
            a.target=address(shares);a.tokenIn=address(shares);a.tokenOut=address(u);
            a.minOutput=shares.previewRedeem(amount)*9960/10000;
            phi.minDeltas[0]=int256(a.minOutput);phi.minDeltas[2]=-int256(amount);
        }
        return(bind(a,phi),phi);
    }
    function run(uint8 kind,uint256 amount,uint256 nonce) internal {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(kind,amount,nonce);
        v.executeOperation(a,phi,sign(a));
    }
    function expectFailure(PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi,bytes4 reason) internal {
        bytes memory sig=sign(a);vm.expectRevert(reason);v.executeOperation(a,phi,sig);
        require(!v.usedNonce(a.nonce),"nonce changed on revert");
    }
    function testSwapAndPaymentAndVault() public {
        run(1,100e6,1);require(w.balanceOf(address(v))==5e18);
        run(2,10e6,2);require(u.balanceOf(PAYEE)==10e6);
        run(3,100e6,3);require(shares.balanceOf(address(v))==100e6);
        run(4,10e6,4);require(shares.balanceOf(address(v))==90e6);
        require(u.allowance(address(v),address(shares))==0 && u.allowance(address(v),address(adapter))==0);
    }
    function testReverseSwap() public {
        run(1,100e6,1);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,1e18,2);
        a.tokenIn=address(w);a.tokenOut=address(u);a.minOutput=19e6;a.spendDebitUsdE8=21e8;
        phi.minDeltas[0]=19e6;phi.minDeltas[1]=-1e18;a=bind(a,phi);
        v.executeOperation(a,phi,sign(a));require(u.balanceOf(address(v))==920e6);
    }
    function testNativeReceipt() public {
        vm.deal(address(v),1e18);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e17,1);
        a.target=PAYEE;a.tokenIn=address(0);a.tokenOut=address(0);a.spendDebitUsdE8=3e8;
        phi.minDeltas[0]=0;phi.minDeltas[3]=-1e17;a=bind(a,phi);
        v.executeOperation(a,phi,sign(a));require(PAYEE.balance==1e17);
    }
    function testAttackUnauthorizedProposal() public {
        // An injected model proposal is still subject to the owner recipient allowlist.
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,10e6,1);
        a.recipient=address(0xBAD);a=bind(a,phi);expectFailure(a,phi,PolicyVaultV3.PayeeNotAllowed.selector);
    }
    function testAttackInvalidPayee() public { testAttackUnauthorizedProposal(); }
    function testAttackTamperedCall() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,10e6,1);
        a.calldataHash=keccak256("approve unlimited instead of transfer");expectFailure(a,phi,PolicyVault.HashMismatch.selector);
    }
    function testSignatureAmountAndPhiBinding() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,100e6,1);
        bytes memory sig=sign(a);a.amount+=1;
        vm.expectRevert(PolicyVault.BadSignature.selector);v.executeOperation(a,phi,sig);
        a.amount-=1;phi.minDeltas[1]-=1;
        vm.expectRevert(PolicyVault.HashMismatch.selector);v.executeOperation(a,phi,sig);
    }
    function testReplayAndExpiry() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,10e6,1);
        bytes memory sig=sign(a);v.executeOperation(a,phi,sig);
        vm.expectRevert(PolicyVault.NonceReplay.selector);v.executeOperation(a,phi,sig);
        (a,phi)=make(2,10e6,2);sig=sign(a);vm.warp(block.timestamp+31);
        vm.expectRevert(PolicyVault.ExpiredApproval.selector);v.executeOperation(a,phi,sig);
    }
    function testAttackStateDrift() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,100e6,1);
        // The explicit Phi is stricter than the DEX minOut, as it can be in a compiled proof.
        phi.minDeltas[1]=int256(5e18*9960/10000);a=bind(a,phi);
        adapter.setOutputPerUsdc(5e16*9950/10000);
        expectFailure(a,phi,PolicyVault.PostConditionFailed.selector);
        require(u.balanceOf(address(v))==1000e6 && w.balanceOf(address(v))==0);
        (,,,,uint256 risk,)=v.sessions(SESSION);require(risk==0 && v.dailySpentUsdE8(block.timestamp/1 days)==0);
    }
    function testAttackSevereSlippage() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,100e6,1);
        bytes memory sig=sign(a);adapter.setOutputPerUsdc(1e16);
        vm.expectRevert(MockSwapAdapter.MinOutputNotMet.selector);v.executeOperation(a,phi,sig);
        require(!v.usedNonce(1) && u.balanceOf(address(v))==1000e6);
    }
    function testAttackCumulativeLoss() public {
        for(uint256 i=1;i<=6;++i) run(1,10e6,i);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,10e6,7);
        expectFailure(a,phi,PolicyVault.SessionRiskLimit.selector);
        (,,,,uint256 used,)=v.sessions(SESSION);require(used==6e8);
    }
    function testAttackExcessiveAllowance() public {
        vm.prank(address(v));shares.approve(address(adapter),type(uint256).max);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,10e6,1);
        expectFailure(a,phi,PolicyVault.PostConditionFailed.selector);
    }
    function testAttackKillSwitch() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,10e6,1);
        bytes memory sig=sign(a);v.pause();vm.expectRevert();v.executeOperation(a,phi,sig);
        v.unpause();v.revokeSession(SESSION);expectFailure(a,phi,PolicyVault.SessionUnavailable.selector);
    }
    function testPaymentFeeDriftAndRedirection() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,10e6,1);
        u.attack(5000,false);expectFailure(a,phi,PolicyVaultV3.ReceiptNotMet.selector);
        require(u.balanceOf(PAYEE)==0 && u.balanceOf(address(v))==1000e6);
        u.attack(0,true);expectFailure(a,phi,PolicyVaultV3.ReceiptNotMet.selector);
    }
    function testPaymentCannotOvercredit() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,10e6,1);
        phi.receiptCredit=a.amount+1;a=bind(a,phi);expectFailure(a,phi,PolicyVaultV3.ReceiptNotMet.selector);
    }
    function testPerPayeeDailyCap() public {
        run(2,25e6,1);run(2,25e6,2);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,1e6,3);
        expectFailure(a,phi,PolicyVault.DailySpendLimit.selector);
    }
    function testVaultRateManipulationAndPaused() public {
        run(3,100e6,1);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(3,10e6,2);
        u.mint(address(shares),100e6);expectFailure(a,phi,PolicyVaultV3.VaultRateOutOfBounds.selector);
    }
    function testPausedVaultAndMissingSharesRevert() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(3,10e6,1);
        bytes memory sig=sign(a);shares.setStopped(true);vm.expectRevert();v.executeOperation(a,phi,sig);
        require(!v.usedNonce(1));
    }
    function testShareRoundingAndNonUnitRate() public {
        u.mint(address(this),100e6);u.approve(address(shares),100e6);shares.deposit(100e6,address(this));
        u.mint(address(shares),1e6); // Rate 1.01 within the approved band.
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(3,10e6,1);
        v.executeOperation(a,phi,sign(a));require(shares.balanceOf(address(v))<10e6);
    }
    function testUnexpectedAssetMovementBeforeExecution() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,10e6,1);
        u.mint(address(v),1);expectFailure(a,phi,PolicyVaultV3.StateDrift.selector);
    }
    function testOwnerOnlyAndPolicyInvalidation() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,10e6,1);
        vm.prank(address(0xBAD));vm.expectRevert();v.pause();
        vm.prank(address(0xBAD));vm.expectRevert();v.authorizeSession(SESSION,31,1e8,10,0);
        v.setPayee(address(u),PAYEE,1e6,1e6);configure();expectFailure(a,phi,PolicyVault.PolicyRevoked.selector);
    }
    function testLegacyPathsDisabled() public {
        PolicyVault.Approval memory a;vm.expectRevert(PolicyVault.ProofRequired.selector);v.executeApprovedSwap(a,"","");
        PolicyVault.ApprovalV2 memory a2;PolicyVault.PostConditionsV2 memory phi;
        vm.expectRevert(PolicyVault.ProofRequired.selector);v.executeApprovedSwapV2(a2,"",phi,"");
    }
    function testRebalanceCooldown() public {
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(1,10e6,1);
        a.rebalance=true;a=bind(a,phi);v.executeOperation(a,phi,sign(a));
        (a,phi)=make(1,10e6,2);a.rebalance=true;a=bind(a,phi);expectFailure(a,phi,PolicyVaultV3.ScopeViolation.selector);
    }
    function testSessionSpendAndActionCaps() public {
        bytes32 limited=keccak256("limited");v.createSession(limited,block.timestamp,block.timestamp+3600,6e8);
        v.authorizeSession(limited,2,20e8,1,0);
        (PolicyVaultV3.Operation memory a,PolicyVaultV3.Constraints memory phi)=make(2,10e6,1);
        a.sessionId=limited;a=bind(a,phi);v.executeOperation(a,phi,sign(a));
        (a,phi)=make(2,10e6,2);a.sessionId=limited;a=bind(a,phi);expectFailure(a,phi,PolicyVaultV3.ScopeViolation.selector);
    }
    function testFuzzPaymentReceiptIsBounded(uint96 raw) public {
        uint256 amount=uint256(raw)%25e6+1;run(2,amount,1);require(u.balanceOf(PAYEE)==amount);
    }
}
