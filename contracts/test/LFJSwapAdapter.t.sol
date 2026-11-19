// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {PolicyVault} from "../src/PolicyVault.sol";
import {LFJSwapAdapter} from "../src/adapters/LFJSwapAdapter.sol";
import {MockUSDC} from "../src/mocks/MockUSDC.sol";
import {MockWAVAX} from "../src/mocks/MockWAVAX.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ISwapAdapter} from "../src/interfaces/ISwapAdapter.sol";
import {ILFJRouter} from "../src/interfaces/ILFJ.sol";

interface LFJVm {
    function chainId(uint256) external;
    function addr(uint256) external returns (address);
    function sign(uint256,bytes32) external returns (uint8,bytes32,bytes32);
    function expectRevert() external;
    function expectRevert(bytes4) external;
    function etch(address,bytes calldata) external;
}

// ABI-compatible test doubles ONLY. Live-fork coverage is separate and uses real LFJ bytecode.
contract TestLFJPair {
    address public token0; address public token1; address public factory;
    constructor(address a,address b,address f) { token0=a; token1=b; factory=f; }
    function getReserves() external view returns(uint112,uint112,uint32) {
        return(uint112(IERC20(token0).balanceOf(address(this))),uint112(IERC20(token1).balanceOf(address(this))),uint32(block.timestamp));
    }
    function pay(address to,uint256 amount) external { require(IERC20(token1).transfer(to,amount)); }
}
contract TestLFJRouter is ILFJRouter {
    address public pool; address public input; address public output;
    uint256 public mode;
    function setup(address p,address a,address b) external { pool=p; input=a; output=b; }
    function setMode(uint256 m) external { mode=m; }
    function getPair(address a,address b) external view returns(address) { return a==input && b==output ? pool : address(0); }
    function getV1Factory() external view returns(address) { return address(this); }
    function getWNATIVE() external view returns(address) { return output; }
    function swapExactTokensForTokens(uint256 amount,uint256 minimum,Path calldata path,address to,uint256 deadline)
        external returns(uint256 result) {
        require(path.versions.length==1 && path.versions[0]==Version.V1 && path.pairBinSteps[0]==0);
        require(path.tokenPath[0]==input && path.tokenPath[1]==output && deadline>=block.timestamp);
        (uint112 ri,uint112 ro,) = TestLFJPair(pool).getReserves();
        result = amount*997*ro/(uint256(ri)*1000+amount*997);
        require(result>=minimum);
        require(IERC20(input).transferFrom(msg.sender,pool,amount));
        TestLFJPair(pool).pay(to,mode==1 ? result-1 : result);
        if (mode==2) revert("ROUTER_FAILURE");
    }
}
contract LFJSwapAdapterTest {
    LFJVm constant vm=LFJVm(address(uint160(uint256(keccak256("hevm cheat code")))));
    // Deterministic unit-test signing key; never used on a public network.
    uint256 constant TEST_KEY=0x1234;
    MockUSDC usdc; MockWAVAX wavax; PolicyVault vault;
    TestLFJRouter dex; TestLFJPair pair; LFJSwapAdapter adapter;
    function setUp() public {
        vm.chainId(43113);
        usdc=new MockUSDC(address(this));wavax=new MockWAVAX(address(this));
        vault=new PolicyVault(address(this),vm.addr(TEST_KEY),address(usdc),address(wavax));
        dex=new TestLFJRouter();pair=new TestLFJPair(address(usdc),address(wavax),address(dex));
        dex.setup(address(pair),address(usdc),address(wavax));
        adapter=new LFJSwapAdapter(address(vault),address(dex),address(pair),address(usdc),address(wavax));
        vault.setRouter(address(adapter),true);
        vault.configurePolicy(keccak256("lfj-unit-policy"),500e6,1000e6,100,block.timestamp+1 days);
        usdc.mint(address(vault),1000e6);usdc.mint(address(pair),10000e6);wavax.mint(address(pair),1000e18);
    }
    function execute(uint256 nonce,uint256 minimum,bytes4 expected) internal {
        bytes memory data=abi.encodeCall(ISwapAdapter.exactInput,(address(usdc),address(wavax),100e6,minimum,address(vault)));
        PolicyVault.Approval memory a=PolicyVault.Approval(vault.activePolicyHash(),keccak256("unit-evidence"),address(adapter),
            address(usdc),address(wavax),100e6,minimum,keccak256(data),nonce,block.timestamp+30);
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(TEST_KEY,vault.hashApproval(a));
        if (expected==bytes4(0xffffffff)) vm.expectRevert();
        else if (expected!=bytes4(0)) vm.expectRevert(expected);
        vault.executeApprovedSwap(a,data,abi.encodePacked(r,s,v));
    }
    function testLFJValidSwapAndBothAllowancesCleared() public {
        uint256 quoted=adapter.quote(address(usdc),address(wavax),100e6);
        execute(1,quoted,bytes4(0));
        require(usdc.balanceOf(address(vault))==900e6);
        require(wavax.balanceOf(address(vault))==quoted);
        require(usdc.allowance(address(vault),address(adapter))==0);
        require(usdc.allowance(address(adapter),address(dex))==0);
        require(usdc.balanceOf(address(adapter))==0 && vault.usedNonce(1));
    }
    function testLFJRejectsUnauthorizedRecipientAndCaller() public {
        vm.expectRevert(LFJSwapAdapter.BadRecipient.selector);
        adapter.exactInput(address(usdc),address(wavax),100e6,1,address(this));
        vm.expectRevert(LFJSwapAdapter.BadRecipient.selector);
        adapter.exactInput(address(usdc),address(wavax),100e6,1,address(vault));
    }
    function testLFJWrongChain() public {
        vm.chainId(43114);vm.expectRevert(LFJSwapAdapter.WrongChain.selector);
        adapter.quote(address(usdc),address(wavax),1e6);
    }
    function testLFJWrongTokenAndZeroQuote() public {
        vm.expectRevert(LFJSwapAdapter.UnsupportedPair.selector);adapter.quote(address(wavax),address(usdc),1e6);
        vm.expectRevert(LFJSwapAdapter.NoLiquidity.selector);adapter.quote(address(usdc),address(wavax),0);
    }
    function testLFJRejectsChangedRoute() public {
        dex.setup(address(0),address(usdc),address(wavax));
        vm.expectRevert(LFJSwapAdapter.InvalidRoute.selector);adapter.quote(address(usdc),address(wavax),1e6);
    }
    function testLFJRejectsChangedRouterBytecode() public {
        vm.etch(address(dex),hex"00");vm.expectRevert(LFJSwapAdapter.InvalidRoute.selector);
        adapter.quote(address(usdc),address(wavax),1e6);
    }
    function testLFJExcessiveMinOutRollsBackNonceBudgetAndFunds() public {
        uint256 quoted=adapter.quote(address(usdc),address(wavax),100e6);
        execute(1,quoted+1,LFJSwapAdapter.MinOutputNotMet.selector);
        require(!vault.usedNonce(1) && vault.dailySpentUsdc(block.timestamp/1 days)==0);
        require(usdc.balanceOf(address(vault))==1000e6);
    }
    function testLFJReportedOutputMismatchReverts() public {
        dex.setMode(1);execute(1,1,LFJSwapAdapter.UnexpectedTransfer.selector);
        require(usdc.allowance(address(adapter),address(dex))==0 && !vault.usedNonce(1));
    }
    function testLFJRouterRevertRollsBackAllAllowancesAndFunds() public {
        dex.setMode(2);execute(1,1,bytes4(0xffffffff));
        require(usdc.allowance(address(vault),address(adapter))==0);
        require(usdc.allowance(address(adapter),address(dex))==0);
        require(usdc.balanceOf(address(vault))==1000e6 && !vault.usedNonce(1));
    }
    function testLFJEmptyLiquidity() public {
        TestLFJPair empty=new TestLFJPair(address(usdc),address(wavax),address(dex));
        dex.setup(address(empty),address(usdc),address(wavax));
        LFJSwapAdapter a=new LFJSwapAdapter(address(vault),address(dex),address(empty),address(usdc),address(wavax));
        vm.expectRevert(LFJSwapAdapter.NoLiquidity.selector);a.quote(address(usdc),address(wavax),1e6);
    }
}
