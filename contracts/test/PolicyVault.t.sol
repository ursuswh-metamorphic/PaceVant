// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {PolicyVault} from "../src/PolicyVault.sol";
import {MockUSDC} from "../src/mocks/MockUSDC.sol";
import {MockWAVAX} from "../src/mocks/MockWAVAX.sol";
import {MockSwapAdapter} from "../src/adapters/MockSwapAdapter.sol";
import {ISwapAdapter} from "../src/interfaces/ISwapAdapter.sol";
import {AdversarialSwapAdapter} from "./AdversarialSwapAdapter.sol";

interface Vm {
    function addr(uint256) external returns (address);
    function sign(uint256,bytes32) external returns (uint8,bytes32,bytes32);
    function warp(uint256) external;
    function chainId(uint256) external;
    function prank(address) external;
    function expectRevert() external;
    function expectRevert(bytes4) external;
    function readFile(string calldata) external view returns (string memory);
    function parseJsonString(string calldata,string calldata) external pure returns (string memory);
    function parseJsonBytes32(string calldata,string calldata) external pure returns (bytes32);
    function parseJsonBytes(string calldata,string calldata) external pure returns (bytes memory);
    function parseJsonAddress(string calldata,string calldata) external pure returns (address);
    function parseUint(string calldata) external pure returns (uint256);
    function etch(address,bytes calldata) external;
}

contract PolicyVaultTest {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    uint256 constant SIGNER_KEY = 0x1234;
    MockUSDC internal usdc;
    MockWAVAX internal wavax;
    MockSwapAdapter internal router;
    PolicyVault internal vault;
    bytes32 constant ROOT = keccak256("real-test-evidence");
    function setUp() public {
        vm.warp(1800000000); vm.chainId(43113);
        usdc = new MockUSDC(address(this)); wavax = new MockWAVAX(address(this));
        router = new MockSwapAdapter(address(this),address(usdc),address(wavax));
        vault = new PolicyVault(address(this),vm.addr(SIGNER_KEY),address(usdc),address(wavax));
        vault.setRouter(address(router),true);
        configure();
        usdc.mint(address(vault),10000e6); wavax.mint(address(router),10000e18);
    }
    function configure() internal {
        vault.configurePolicy(keccak256("mandate-v1"),500e6,1000e6,100,block.timestamp + 1 days);
    }
    function make(uint256 nonce,uint256 amount) internal view returns (PolicyVault.Approval memory a,bytes memory data) {
        uint256 minOut = router.quote(address(usdc),address(wavax),amount)*9960/10000;
        data = abi.encodeCall(ISwapAdapter.exactInput,(address(usdc),address(wavax),amount,minOut,address(vault)));
        a = PolicyVault.Approval(vault.activePolicyHash(),ROOT,address(router),address(usdc),address(wavax),
            amount,minOut,keccak256(data),nonce,block.timestamp+30);
    }
    function sig(PolicyVault.Approval memory a) internal returns (bytes memory) {
        (uint8 v,bytes32 r,bytes32 s) = vm.sign(SIGNER_KEY,vault.hashApproval(a));
        return abi.encodePacked(r,s,v);
    }
    function swap(uint256 nonce,uint256 amount) internal {
        (PolicyVault.Approval memory a,bytes memory data) = make(nonce,amount);
        vault.executeApprovedSwap(a,data,sig(a));
    }
    function testB01ValidSwap() public {
        swap(1,500e6);
        require(usdc.balanceOf(address(vault)) == 9500e6);
        require(wavax.balanceOf(address(vault)) == 25e18);
        require(vault.usedNonce(1)); require(vault.dailySpentUsdc(block.timestamp/1 days)==500e6);
        require(usdc.allowance(address(vault),address(router))==0);
    }
    function testB02Replay() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); bytes memory s=sig(a);
        vault.executeApprovedSwap(a,data,s);
        vm.expectRevert(PolicyVault.NonceReplay.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testB03ChangedCalldata() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); bytes memory s=sig(a);
        data[35]=bytes1(uint8(data[35])^1);
        vm.expectRevert(PolicyVault.HashMismatch.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testB04ChangedMinOutStruct() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); a.minAmountOut++;
        bytes memory s=sig(a);
        vm.expectRevert(PolicyVault.InvalidCall.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testB04ChangedToken() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); a.tokenIn=address(wavax);
        bytes memory s=sig(a); vm.expectRevert(PolicyVault.InvalidCall.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testB04UnlistedRouter() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); a.router=address(0xBAD);
        bytes memory s=sig(a); vm.expectRevert(PolicyVault.InvalidCall.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testB05RevokedAttestor() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); bytes memory s=sig(a);
        vault.setAttestor(address(0)); vm.expectRevert(PolicyVault.PolicyRevoked.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testB05ChangedPolicy() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); bytes memory s=sig(a);
        configure(); vm.expectRevert(PolicyVault.PolicyRevoked.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testOldPolicyDoesNotReactivate() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); bytes memory s=sig(a);
        vault.setRouter(address(router),false); vault.setRouter(address(router),true); configure();
        require(a.policyHash!=vault.activePolicyHash());
        vm.expectRevert(PolicyVault.PolicyRevoked.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testB06Expired() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); bytes memory s=sig(a); vm.warp(block.timestamp+31);
        vm.expectRevert(PolicyVault.ExpiredApproval.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testB06WrongChain() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); bytes memory s=sig(a); vm.chainId(1);
        vm.expectRevert(PolicyVault.BadSignature.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testWrongVaultDomain() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,200e6); bytes memory s=sig(a);
        PolicyVault other = new PolicyVault(address(this),vm.addr(SIGNER_KEY),address(usdc),address(wavax));
        require(other.hashApproval(a)!=vault.hashApproval(a));
        a.policyHash=other.activePolicyHash();
        vm.expectRevert(); other.executeApprovedSwap(a,data,s);
    }
    function testB07TradeLimit() public {
        (PolicyVault.Approval memory a,bytes memory data) = make(1,501e6); bytes memory s=sig(a);
        vm.expectRevert(PolicyVault.TradeSizeLimit.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testB08DailyRace700Plus200Plus200() public {
        swap(1,500e6); swap(2,200e6); swap(3,200e6);
        (PolicyVault.Approval memory a,bytes memory data)=make(4,200e6);bytes memory s=sig(a);
        vm.expectRevert(PolicyVault.DailySpendLimit.selector); vault.executeApprovedSwap(a,data,s);
        require(vault.dailySpentUsdc(block.timestamp/1 days)==900e6); require(!vault.usedNonce(4));
    }
    function testDailyBoundaryResetsUTC() public {
        swap(1,500e6);swap(2,500e6);vm.warp(1800057600);swap(3,500e6);
        // Do not reuse block.timestamp in a test frame across vm.warp (optimizer treats it as constant).
        require(vault.dailySpentUsdc(1800057600/1 days)==500e6);
    }
    function testB09MinOutRollback() public {
        (PolicyVault.Approval memory a,bytes memory data)=make(1,500e6); bytes memory s=sig(a);
        router.setOutputPerUsdc(492e14); // 24.6 < minOut 24.9
        vm.expectRevert(MockSwapAdapter.MinOutputNotMet.selector); vault.executeApprovedSwap(a,data,s);
        require(usdc.balanceOf(address(vault))==10000e6);require(wavax.balanceOf(address(vault))==0);
        require(!vault.usedNonce(1));require(vault.dailySpentUsdc(block.timestamp/1 days)==0);
        require(usdc.allowance(address(vault),address(router))==0);
    }
    function testB10BadRecipient() public {
        (PolicyVault.Approval memory a,)=make(1,200e6);
        bytes memory data=abi.encodeCall(ISwapAdapter.exactInput,(address(usdc),address(wavax),a.amountIn,a.minAmountOut,address(0xBAD)));
        a.calldataHash=keccak256(data); bytes memory s=sig(a);
        vm.expectRevert(PolicyVault.InvalidCall.selector); vault.executeApprovedSwap(a,data,s);
    }
    function testPaused() public {
        (PolicyVault.Approval memory a,bytes memory data)=make(1,200e6);bytes memory s=sig(a);vault.pause();
        vm.expectRevert();vault.executeApprovedSwap(a,data,s);
    }
    function testMalformedCalldata() public {
        (PolicyVault.Approval memory a,bytes memory data)=make(1,200e6);data=bytes.concat(data,hex"00");
        a.calldataHash=keccak256(data);bytes memory s=sig(a);
        vm.expectRevert(PolicyVault.InvalidCall.selector);vault.executeApprovedSwap(a,data,s);
    }
    function testBadSigner() public {
        (PolicyVault.Approval memory a,bytes memory data)=make(1,200e6);
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(0x5678,vault.hashApproval(a));
        vm.expectRevert(PolicyVault.BadSignature.selector);vault.executeApprovedSwap(a,data,abi.encodePacked(r,s,v));
    }
    function testOwnerOnlyConfiguration() public {
        vm.prank(address(0xBAD));vm.expectRevert();vault.setRouter(address(router),false);
    }
    function testWrongSelectorEvenWithSignedHash() public {
        (PolicyVault.Approval memory a,bytes memory data)=make(1,200e6);data[0]=0xff;
        a.calldataHash=keccak256(data);bytes memory s=sig(a);
        vm.expectRevert(PolicyVault.InvalidCall.selector);vault.executeApprovedSwap(a,data,s);
    }
    function adversarial(uint256 mode) internal returns(AdversarialSwapAdapter evil,PolicyVault.Approval memory a,bytes memory data) {
        evil=new AdversarialSwapAdapter(mode);vault.setRouter(address(evil),true);configure();
        wavax.mint(address(evil),100e18);
        (a,)=make(1,200e6);a.router=address(evil);
        data=abi.encodeCall(ISwapAdapter.exactInput,(address(usdc),address(wavax),a.amountIn,a.minAmountOut,address(vault)));
        a.calldataHash=keccak256(data);
    }
    function testPostconditionRejectsAdapterUnderpayment() public {
        (AdversarialSwapAdapter evil,PolicyVault.Approval memory a,bytes memory data)=adversarial(0);
        bytes memory s=sig(a);vm.expectRevert(PolicyVault.MinOutputNotMet.selector);vault.executeApprovedSwap(a,data,s);
        require(usdc.balanceOf(address(vault))==10000e6);require(!vault.usedNonce(1));
        require(usdc.allowance(address(vault),address(evil))==0);
    }
    function testPostconditionRejectsWrongInputDelta() public {
        (,PolicyVault.Approval memory a,bytes memory data)=adversarial(1);
        bytes memory s=sig(a);vm.expectRevert(PolicyVault.UnexpectedTransfer.selector);vault.executeApprovedSwap(a,data,s);
        require(usdc.balanceOf(address(vault))==10000e6);require(!vault.usedNonce(1));
    }
    function testReentrancyBlockedAndAllowanceCleared() public {
        (AdversarialSwapAdapter evil,PolicyVault.Approval memory a,bytes memory data)=adversarial(2);
        bytes memory s=sig(a);evil.setReentry(abi.encodeCall(PolicyVault.executeApprovedSwap,(a,data,s)));
        vault.executeApprovedSwap(a,data,s);
        require(!evil.reentered());require(usdc.allowance(address(vault),address(evil))==0);
    }
    function testFuzzExactDeltas(uint96 raw) public {
        uint256 amount=uint256(raw)%500e6+1;swap(1,amount);
        require(usdc.balanceOf(address(vault))==10000e6-amount);
        require(usdc.allowance(address(vault),address(router))==0);
    }
}
