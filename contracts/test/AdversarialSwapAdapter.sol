// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {ISwapAdapter} from "../src/interfaces/ISwapAdapter.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// @dev Test postconditions even if an owner allowlists a misbehaving adapter.
contract AdversarialSwapAdapter is ISwapAdapter {
    uint256 public mode;
    bool public reentered;
    bytes public reentryData;
    constructor(uint256 value) { mode=value; }
    function setReentry(bytes calldata value) external { reentryData=value; }
    function quote(address,address,uint256 amount) external pure returns(uint256) { return amount*5e10; }
    function exactInput(address input,address output,uint256 amount,uint256 minOut,address recipient)
        external returns(uint256)
    {
        require(IERC20(input).allowance(msg.sender,address(this))==amount,"ALLOWANCE_NOT_EXACT");
        IERC20(input).transferFrom(msg.sender,address(this),mode==1 ? amount-1 : amount);
        if(mode==2) (reentered,)=msg.sender.call(reentryData);
        uint256 result=mode==0 ? minOut-1 : minOut;
        IERC20(output).transfer(recipient,result);
        return result;
    }
}
