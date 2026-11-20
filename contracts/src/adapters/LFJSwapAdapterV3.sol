// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {LFJSwapAdapter} from "./LFJSwapAdapter.sol";

/// @notice Explicit new adapter deployment for the same validated V1 pool, in both directions.
contract LFJSwapAdapterV3 is LFJSwapAdapter {
    constructor(address vault,address router,address pool,address input,address output)
        LFJSwapAdapter(vault,router,pool,input,output) {}
    function adapterVersion() public pure override returns(string memory) { return "lfj-v1-fuji-v3-bidirectional"; }
    function _validate(address input,address output) internal view override {
        if (!((input==usdc && output==wavax) || (input==wavax && output==usdc))) revert UnsupportedPair();
        super._validate(usdc,wavax);
    }
}
