// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {PolicyVault} from "../src/PolicyVault.sol";
import {MockUSDC} from "../src/mocks/MockUSDC.sol";
import {MockWAVAX} from "../src/mocks/MockWAVAX.sol";
import {MockSwapAdapter} from "../src/adapters/MockSwapAdapter.sol";
import {ISwapAdapter} from "../src/interfaces/ISwapAdapter.sol";
import {AdversarialSwapAdapter} from "./AdversarialSwapAdapter.sol";
import {Vm} from "./PolicyVault.t.sol";

contract PolicyVaultV2Test {
    Vm internal constant vm=Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    uint256 constant KEY=0x1234;
    bytes32 constant SESSION=keccak256("TEST_ONLY_session");
    MockUSDC u; MockWAVAX w; MockSwapAdapter router; PolicyVault vault;
    function setUp() public {
        vm.warp(1800000000); vm.chainId(31337);
        u=new MockUSDC(address(this)); w=new MockWAVAX(address(this));
        router=new MockSwapAdapter(address(this),address(u),address(w));
        vault=new PolicyVault(address(this),vm.addr(KEY),address(u),address(w));
        vault.setRouter(address(router),true); configureProof(address(router),10e8);
        configure(); vault.createSession(SESSION,block.timestamp,block.timestamp+3600,6e8);
        u.mint(address(vault),10000e6); w.mint(address(vault),100e18);
        w.mint(address(router),10000e18); u.mint(address(router),100000e6);
    }
    function configureProof(address adapter,uint256 global) internal {
        vault.configureProofPolicy(adapter,PolicyVault.ProofPolicy(10e18,300,0,100,40,60,10e8,global,keccak256("TRUSTED_TEST_ORACLE"),false));
    }
    function configure() internal {
        vault.configurePolicy(keccak256("TEST_ONLY_mandate"),700e6,1000e6,100,block.timestamp+1 days);
    }
    function make(uint256 nonce,uint256 debit,bool reverse) internal view returns(PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi) {
        address input=reverse?address(w):address(u); address output=reverse?address(u):address(w);
        uint256 amount=reverse?1e18:100e6; uint256 minOut=router.quote(input,output,amount)*9900/10000;
        data=abi.encodeCall(ISwapAdapter.exactInput,(input,output,amount,minOut,address(vault)));
        phi.balanceBounds=new PolicyVault.BalanceBound[](2); phi.allowanceCaps=new PolicyVault.AllowanceCap[](2);
        address first=address(u)<address(w)?address(u):address(w); address second=address(u)<address(w)?address(w):address(u);
        for(uint256 i;i<2;i++) {
            address asset=i==0?first:second;
            phi.balanceBounds[i]=PolicyVault.BalanceBound(asset,asset==input?-int256(amount):int256(router.quote(input,output,amount)*9960/10000));
            phi.allowanceCaps[i]=PolicyVault.AllowanceCap(asset,address(router),0);
        }
        a=PolicyVault.ApprovalV2(keccak256("intent"),keccak256(data),vault.activePolicyHash(),keccak256("effects"),
            keccak256("certified-proof"),keccak256(abi.encode(phi)),SESSION,debit,nonce,block.timestamp+30,
            address(router),input,output,amount,minOut);
    }
    function sign(PolicyVault.ApprovalV2 memory a) internal returns(bytes memory) {
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(KEY,vault.hashApprovalV2(a)); return abi.encodePacked(r,s,v);
    }
    function swap(uint256 nonce,uint256 debit) internal {
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(nonce,debit,false);
        vault.executeApprovedSwapV2(a,data,phi,sign(a));
    }
    function expectSwapRevert(uint256 nonce,uint256 debit,bytes4 reason) internal {
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(nonce,debit,false);
        bytes memory signature=sign(a);
        if(reason==bytes4(0)) vm.expectRevert(); else vm.expectRevert(reason);
        vault.executeApprovedSwapV2(a,data,phi,signature);
    }
    function used(bytes32 id) internal view returns(uint256 amount) { (,,,,amount,)=vault.sessions(id); }
    function unchanged(uint256 nonce,uint256 ub,uint256 wb,uint256 sessionUsed,uint256 globalUsed,uint256 spent) internal view {
        require(!vault.usedNonce(nonce));require(u.balanceOf(address(vault))==ub);require(w.balanceOf(address(vault))==wb);
        require(used(SESSION)==sessionUsed);require(vault.globalDailyRiskUsedUsdE8(block.timestamp/1 days)==globalUsed);
        require(vault.dailySpentUsdc(block.timestamp/1 days)==spent);require(u.allowance(address(vault),address(router))==0);
    }
    function testNormalExactDeltasAndCounters() public {
        swap(1,2e8);require(u.balanceOf(address(vault))==9900e6);require(w.balanceOf(address(vault))==105e18);
        require(used(SESSION)==2e8);require(vault.globalDailyRiskUsedUsdE8(block.timestamp/1 days)==2e8);
        require(vault.dailySpentUsdc(block.timestamp/1 days)==100e6);require(vault.usedNonce(1));
        require(u.allowance(address(vault),address(router))==0);
    }
    function testReverseHasSeparateCapAndNoUsdcSpend() public {
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(1,1e8,true);
        vault.executeApprovedSwapV2(a,data,phi,sign(a));
        require(u.balanceOf(address(vault))==10020e6);require(w.balanceOf(address(vault))==99e18);
        require(vault.dailySpentUsdc(block.timestamp/1 days)==0);require(w.allowance(address(vault),address(router))==0);
    }
    function testLegacyPathPermanentlyDisabled() public {
        PolicyVault.Approval memory a;
        vm.expectRevert(PolicyVault.ProofRequired.selector);vault.executeApprovedSwap(a,"","");
        configure();vm.expectRevert(PolicyVault.ProofRequired.selector);vault.executeApprovedSwap(a,"","");
    }
    function testPhiStricterThanLegacyMinOutRollsBack() public {
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(1,2e8,false);
        router.setOutputPerUsdc(5e16*9950/10000); // >= signed minOut but below compiled Phi
        bytes memory signature=sign(a);
        vm.expectRevert(PolicyVault.PostConditionFailed.selector);vault.executeApprovedSwapV2(a,data,phi,signature);
        unchanged(1,10000e6,100e18,0,0,0);
    }
    function testBetterOutputAndInToleranceDrift() public {
        router.setOutputPerUsdc(51e15);swap(1,1e8);
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(2,1e8,false);
        router.setOutputPerUsdc(51e15*9980/10000);vault.executeApprovedSwapV2(a,data,phi,sign(a));
        require(used(SESSION)==2e8);
    }
    function testSessionCumulativeLimit() public {
        swap(1,3e8);swap(2,3e8);
        expectSwapRevert(3,1,PolicyVault.SessionRiskLimit.selector);
        unchanged(3,9800e6,110e18,6e8,6e8,200e6);
    }
    function testGlobalCapAcrossNewOwnerSession() public {
        swap(1,6e8);
        bytes32 other=keccak256("other");vault.createSession(other,block.timestamp,block.timestamp+3600,6e8);
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(2,5e8,false);
        a.sessionId=other;bytes memory signature=sign(a);
        vm.expectRevert(PolicyVault.GlobalRiskLimit.selector);vault.executeApprovedSwapV2(a,data,phi,signature);
        require(used(other)==0);unchanged(2,9900e6,105e18,6e8,6e8,100e6);
    }
    function testSessionCannotRecycleAfterRevoke() public {
        swap(1,2e8);vault.revokeSession(SESSION);
        vm.expectRevert(PolicyVault.InvalidConfiguration.selector);vault.createSession(SESSION,block.timestamp,block.timestamp+3600,6e8);
        expectSwapRevert(2,1e8,PolicyVault.SessionUnavailable.selector);require(used(SESSION)==2e8);
    }
    function testPolicyRotationAndPauseReject() public {
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(1,2e8,false);
        bytes memory signature=sign(a);configure();vm.expectRevert(PolicyVault.PolicyRevoked.selector);vault.executeApprovedSwapV2(a,data,phi,signature);
        vault.pause();expectSwapRevert(2,1e8,bytes4(0));
    }
    function testAgentCannotManageSessionsOrPolicy() public {
        vm.prank(address(0xBAD));vm.expectRevert();vault.createSession(keccak256("invented"),block.timestamp,block.timestamp+3600,1);
        vm.prank(address(0xBAD));vm.expectRevert();vault.revokeSession(SESSION);
        vm.prank(address(0xBAD));vm.expectRevert();configureProof(address(router),10e8);
    }
    function testMissingOrDuplicateAssetRejected() public {
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(1,2e8,false);
        phi.balanceBounds[1].asset=phi.balanceBounds[0].asset;a.postConditionsHash=keccak256(abi.encode(phi));bytes memory signature=sign(a);
        vm.expectRevert(PolicyVault.InvalidPostConditions.selector);vault.executeApprovedSwapV2(a,data,phi,signature);
        unchanged(1,10000e6,100e18,0,0,0);
    }
    function testNonzeroAllowanceCapRejected() public {
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(1,2e8,false);
        phi.allowanceCaps[0].maxRemaining=1;a.postConditionsHash=keccak256(abi.encode(phi));bytes memory signature=sign(a);
        vm.expectRevert(PolicyVault.InvalidPostConditions.selector);vault.executeApprovedSwapV2(a,data,phi,signature);
    }
    function testEverySignedFieldMutationRejected() public {
        for(uint256 field;field<15;field++) {
            (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(field+1,1e8,false);
            bytes memory signature=sign(a);
            assembly ("memory-safe") { let p:=add(a,mul(field,32)) mstore(p,xor(mload(p),1)) }
            vm.expectRevert();vault.executeApprovedSwapV2(a,data,phi,signature);
            require(!vault.usedNonce(field+1));
        }
        require(used(SESSION)==0);require(u.balanceOf(address(vault))==10000e6);
    }
    function testChangedPhiCalldataAndDomainReject() public {
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(1,1e8,false);
        bytes memory signature=sign(a);phi.balanceBounds[0].minDelta++;
        vm.expectRevert(PolicyVault.HashMismatch.selector);vault.executeApprovedSwapV2(a,data,phi,signature);
        phi.balanceBounds[0].minDelta--;data[35]=bytes1(uint8(data[35])^1);
        vm.expectRevert(PolicyVault.HashMismatch.selector);vault.executeApprovedSwapV2(a,data,phi,signature);
        data[35]=bytes1(uint8(data[35])^1);vm.chainId(43113);
        vm.expectRevert(PolicyVault.BadSignature.selector);vault.executeApprovedSwapV2(a,data,phi,signature);
    }
    function testReplayRevokedAttestorAndExpiry() public {
        swap(1,1e8);expectSwapRevert(1,1e8,PolicyVault.NonceReplay.selector);
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(2,1e8,false);
        bytes memory signature=sign(a);vm.warp(block.timestamp+31);
        vm.expectRevert(PolicyVault.ExpiredApproval.selector);vault.executeApprovedSwapV2(a,data,phi,signature);
        vault.setAttestor(address(0));expectSwapRevert(3,1e8,PolicyVault.PolicyRevoked.selector);
    }
    function testFujiRejectsUnapprovedTestConfig() public {
        vm.chainId(43113);vm.expectRevert(PolicyVault.InvalidConfiguration.selector);configureProof(address(router),10e8);
    }
    function swapAmount(uint256 nonce,uint256 amount) internal {
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(nonce,0,false);
        a.amountIn=amount;a.minAmountOut=router.quote(address(u),address(w),amount)*9960/10000;
        data=abi.encodeCall(ISwapAdapter.exactInput,(address(u),address(w),amount,a.minAmountOut,address(vault)));
        a.calldataHash=keccak256(data);
        for(uint256 i;i<2;i++) phi.balanceBounds[i].minDelta=phi.balanceBounds[i].asset==address(u)?-int256(amount):int256(a.minAmountOut);
        a.postConditionsHash=keccak256(abi.encode(phi));vault.executeApprovedSwapV2(a,data,phi,sign(a));
    }
    function attemptAmount(uint256 nonce,uint256 amount) external {require(msg.sender==address(this));swapAmount(nonce,amount);}
    function testV2DailyRace700Plus200Plus200Atomic() public {
        swapAmount(1,700e6);swapAmount(2,200e6);
        vm.expectRevert(PolicyVault.DailySpendLimit.selector);this.attemptAmount(3,200e6);
        unchanged(3,9100e6,145e18,0,0,900e6);
    }
    function testDailyRiskUtcRolloverDoesNotResetSession() public {
        swap(1,2e8);uint256 nextDay=block.timestamp/1 days+1;vm.warp(nextDay*1 days);
        require(used(SESSION)==2e8);require(vault.globalDailyRiskUsedUsdE8(nextDay)==0);
        require(vault.dailySpentUsdc(nextDay)==0);
    }
    function testReverseDisabledUntilOwnerDefinesCap() public {
        PolicyVault.ProofPolicy memory p=PolicyVault.ProofPolicy(0,300,0,100,40,60,10e8,10e8,keccak256("TRUSTED_TEST_ORACLE"),false);
        vault.configureProofPolicy(address(router),p);configure();bytes32 id=keccak256("new-session");
        vault.createSession(id,block.timestamp,block.timestamp+3600,6e8);
        (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(1,0,true);
        a.sessionId=id;bytes memory signature=sign(a);
        vm.expectRevert(PolicyVault.TradeSizeLimit.selector);vault.executeApprovedSwapV2(a,data,phi,signature);
        require(!vault.usedNonce(1));require(w.balanceOf(address(vault))==100e18);
    }
    function testAdversarialAdaptersAndReentry() public {
        for(uint256 mode;mode<3;mode++) {
            AdversarialSwapAdapter bad=new AdversarialSwapAdapter(mode);
            vault.setRouter(address(bad),true);configureProof(address(bad),10e8);configure();
            bytes32 id=keccak256(abi.encode(mode));vault.createSession(id,block.timestamp,block.timestamp+3600,6e8);
            w.mint(address(bad),100e18);
            (PolicyVault.ApprovalV2 memory a,bytes memory data,PolicyVault.PostConditionsV2 memory phi)=make(mode+1,1e8,false);
            a.adapter=address(bad);a.sessionId=id;
            for(uint256 i;i<2;i++) {
                phi.allowanceCaps[i].spender=address(bad);
                if(phi.balanceBounds[i].asset==address(w))phi.balanceBounds[i].minDelta=int256(a.minAmountOut);
            }
            a.postConditionsHash=keccak256(abi.encode(phi));bytes memory signature=sign(a);
            bad.setReentry(abi.encodeCall(PolicyVault.executeApprovedSwapV2,(a,data,phi,signature)));
            if(mode<2) vm.expectRevert();
            vault.executeApprovedSwapV2(a,data,phi,signature);
            require(!bad.reentered());require(u.allowance(address(vault),address(bad))==0);
            if(mode<2) {require(!vault.usedNonce(mode+1));require(used(id)==0);require(u.balanceOf(address(vault))==10000e6);}
            else {require(vault.usedNonce(mode+1));require(used(id)==1e8);}
        }
    }
    function testFuzzBudgetInvariant(uint64 first,uint64 second) public {
        uint256 a=uint256(first)%6e8;uint256 b=uint256(second)%6e8;
        swap(1,a);
        if(a+b>6e8) {expectSwapRevert(2,b,PolicyVault.SessionRiskLimit.selector);require(used(SESSION)==a);}
        else {swap(2,b);require(used(SESSION)==a+b);}
        require(used(SESSION)<=6e8);require(vault.globalDailyRiskUsedUsdE8(block.timestamp/1 days)<=10e8);
    }
    function testGoldenPythonAbiAndEip712() public {
        string memory raw=vm.readFile("fixtures/v2_1/golden.json");
        PolicyVault.ApprovalV2 memory a=abi.decode(vm.parseJsonBytes(raw,".approval_abi"),(PolicyVault.ApprovalV2));
        PolicyVault.PostConditionsV2 memory phi=abi.decode(vm.parseJsonBytes(raw,".phi_abi"),(PolicyVault.PostConditionsV2));
        require(keccak256(abi.encode(phi))==vm.parseJsonBytes32(raw,".phi_hash"));
        address target=vm.parseJsonAddress(raw,".domain.verifyingContract");vm.etch(target,address(vault).code);
        require(PolicyVault(target).hashApprovalV2(a)==vm.parseJsonBytes32(raw,".typed_data_hash"));
    }
}
