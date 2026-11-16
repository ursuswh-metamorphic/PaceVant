// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {Vm} from "./PolicyVault.t.sol";
import {PolicyVault} from "../src/PolicyVault.sol";
import {MockUSDC} from "../src/mocks/MockUSDC.sol";
import {MockWAVAX} from "../src/mocks/MockWAVAX.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

contract PDRGoldenVectorTest {
    Vm constant vm=Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    function testPythonGoldenDigestAndSignature() public {
        string memory json=vm.readFile("fixtures/eip712_golden/vector.json");
        vm.chainId(43113);
        MockUSDC u=new MockUSDC(address(this));MockWAVAX w=new MockWAVAX(address(this));
        PolicyVault deployed=new PolicyVault(address(this),vm.parseJsonAddress(json,".signer"),address(u),address(w));
        address target=vm.parseJsonAddress(json,".domain.verifyingContract");
        vm.etch(target,address(deployed).code);
        PolicyVault.Approval memory a=PolicyVault.Approval(
            vm.parseJsonBytes32(json,".approval.policyHash"),vm.parseJsonBytes32(json,".approval.evidenceRoot"),
            vm.parseJsonAddress(json,".approval.router"),vm.parseJsonAddress(json,".approval.tokenIn"),
            vm.parseJsonAddress(json,".approval.tokenOut"),vm.parseUint(vm.parseJsonString(json,".approval.amountIn")),
            vm.parseUint(vm.parseJsonString(json,".approval.minAmountOut")),vm.parseJsonBytes32(json,".approval.calldataHash"),
            vm.parseUint(vm.parseJsonString(json,".approval.nonce")),vm.parseUint(vm.parseJsonString(json,".approval.deadline")));
        bytes32 h=PolicyVault(target).hashApproval(a);
        require(h==vm.parseJsonBytes32(json,".typed_data_hash"),"PYTHON_SOLIDITY_DIGEST_MISMATCH");
        require(ECDSA.recover(h,vm.parseJsonBytes(json,".signature"))==vm.parseJsonAddress(json,".signer"),"WRONG_RECOVERY");
        require(keccak256(vm.parseJsonBytes(json,".router_calldata"))==a.calldataHash,"CALLDATA_MISMATCH");
        require(keccak256(bytes(vm.readFile("fixtures/eip712_golden/manifest.canonical.json")))==a.evidenceRoot,"MANIFEST_MISMATCH");
    }
}
