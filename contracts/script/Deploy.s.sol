// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {PolicyVault} from "../src/PolicyVault.sol";
import {MockUSDC} from "../src/mocks/MockUSDC.sol";
import {MockWAVAX} from "../src/mocks/MockWAVAX.sol";
import {MockSwapAdapter} from "../src/adapters/MockSwapAdapter.sol";

interface ScriptVm {
    function envUint(string calldata) external returns (uint256);
    function envAddress(string calldata) external returns (address);
    function addr(uint256) external returns (address);
    function startBroadcast(uint256) external;
    function stopBroadcast() external;
}
/// @notice Alternative operator script. Python CLI additionally saves the deployment manifest needed by B.
contract Deploy {
    ScriptVm constant vm=ScriptVm(address(uint160(uint256(keccak256("hevm cheat code")))));
    function run() external returns (PolicyVault vault,MockSwapAdapter adapter,MockUSDC usdc,MockWAVAX wavax) {
        require(block.chainid==43113 || block.chainid==31337,"TEST_CHAINS_ONLY");
        uint256 key=vm.envUint("B_FUJI_OWNER_PRIVATE_KEY");address admin=vm.addr(key);
        address attestor=vm.envAddress("B_FUJI_ATTESTOR_ADDRESS");
        require(attestor!=address(0) && attestor!=admin,"SEPARATE_ATTESTOR_REQUIRED");
        vm.startBroadcast(key);
        usdc=new MockUSDC(admin);wavax=new MockWAVAX(admin);
        adapter=new MockSwapAdapter(admin,address(usdc),address(wavax));
        vault=new PolicyVault(admin,attestor,address(usdc),address(wavax));
        vault.setRouter(address(adapter),true);
        vault.configurePolicy(keccak256("mandate_demo_v1.1"),500e6,1000e6,100,block.timestamp+7 days);
        usdc.mint(address(vault),7700e6);wavax.mint(address(vault),115e18);wavax.mint(address(adapter),100000e18);
        vm.stopBroadcast();
    }
}
