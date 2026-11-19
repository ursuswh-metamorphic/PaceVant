import { readFileSync } from "node:fs";
import { encodeAbiParameters, hashTypedData, keccak256, recoverTypedDataAddress } from "viem";

const v = JSON.parse(readFileSync(new URL("../../../fixtures/v2_1/golden.json", import.meta.url)));
const fields = [
  ["intentHash","bytes32"], ["calldataHash","bytes32"], ["policyHash","bytes32"],
  ["evidenceRoot","bytes32"], ["proofContextHash","bytes32"], ["postConditionsHash","bytes32"],
  ["sessionId","bytes32"], ["riskDebitUsdE8","uint256"], ["nonce","uint256"], ["deadline","uint256"],
  ["adapter","address"], ["tokenIn","address"], ["tokenOut","address"], ["amountIn","uint256"], ["minAmountOut","uint256"],
].map(([name,type])=>({name,type}));
const data = { domain:v.domain, types:{ApprovalV2:fields}, primaryType:"ApprovalV2", message:v.approval };
if (hashTypedData(data)!==v.typed_data_hash) throw new Error("V2 EIP-712 digest mismatch");
if ((await recoverTypedDataAddress({...data,signature:v.signature})).toLowerCase()!==v.signer.toLowerCase()) throw new Error("V2 signer mismatch");
const abi = encodeAbiParameters([{type:"tuple",components:[
  {name:"balanceBounds",type:"tuple[]",components:[{name:"asset",type:"address"},{name:"minDelta",type:"int256"}]},
  {name:"allowanceCaps",type:"tuple[]",components:[{name:"token",type:"address"},{name:"spender",type:"address"},{name:"maxRemaining",type:"uint256"}]},
]}],[{balanceBounds:v.phi.balance_bounds.map(b=>({asset:b.asset,minDelta:BigInt(b.min_delta)})),
      allowanceCaps:v.phi.allowance_caps.map(a=>({token:a.token,spender:a.spender,maxRemaining:BigInt(a.max_remaining)}))}]);
if (abi!==v.phi_abi || keccak256(abi)!==v.phi_hash) throw new Error("V2 Phi canonical ABI mismatch");
if (hashTypedData({...data,domain:{...v.domain,version:"1"}})===v.typed_data_hash) throw new Error("Domain version isolation failed");
console.log("PASS V2 Python ↔ viem Phi ABI, EIP-712 digest, signer and version isolation");
