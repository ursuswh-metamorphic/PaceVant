import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {encodeAbiParameters,hashTypedData,keccak256} from 'viem';
const v=JSON.parse(readFileSync(new URL('../../../fixtures/mvp/hash-vector.json',import.meta.url),'utf8'));
const domain={name:'TreasuryPolicyVault',version:'3',chainId:v.chain_id,verifyingContract:v.treasury};
const message=Object.fromEntries(v.fields.map(({name,type})=>[name,type.startsWith('uint')?BigInt(v.operation[name]):v.operation[name]]));
const payload={domain,types:{Operation:v.fields},primaryType:'Operation',message};
assert.equal(hashTypedData(payload),v.typed_data_hash);
const phiAbi=encodeAbiParameters([{type:'tuple',components:[{type:'uint256[4]'},{type:'int256[4]'},{type:'uint256'},{type:'uint256'}]}],
  [[v.phi.before_balances.map(BigInt),v.phi.min_deltas.map(BigInt),BigInt(v.phi.receipt_credit),BigInt(v.phi.max_wavax_balance)]]);
assert.equal(phiAbi,v.phi_abi);assert.equal(keccak256(phiAbi),v.phi_hash);
assert.notEqual(hashTypedData({...payload,message:{...message,amount:message.amount+1n}}),v.typed_data_hash);
assert.notEqual(hashTypedData({...payload,message:{...message,recipient:v.treasury}}),v.typed_data_hash);
assert.notEqual(hashTypedData({...payload,domain:{...domain,version:'2'}}),v.typed_data_hash);
console.log('PASS MVP Python ↔ viem exact operation, receipt Phi and EIP-712 domain isolation');
