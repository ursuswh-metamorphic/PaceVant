// Cross-language contract test: Python-produced fixture, viem digest and signer.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { hashTypedData, keccak256, recoverTypedDataAddress } from "viem";
const v = JSON.parse(readFileSync("fixtures/eip712_golden/vector.json", "utf8"));
const names = ["policyHash", "evidenceRoot", "router", "tokenIn", "tokenOut", "amountIn", "minAmountOut", "calldataHash", "nonce", "deadline"];
const types = ["bytes32", "bytes32", "address", "address", "address", "uint256", "uint256", "bytes32", "uint256", "uint256"];
const approval = Object.fromEntries(names.map((n, i) => [n, types[i] === "uint256" ? BigInt(v.approval[n]) : v.approval[n]]));
const data = { domain: v.domain, primaryType: "Approval", types: { Approval: names.map((name, i) => ({ name, type: types[i] })) }, message: approval };
assert.equal(hashTypedData(data), v.typed_data_hash);
assert.equal((await recoverTypedDataAddress({ ...data, signature: v.signature })).toLowerCase(), v.signer.toLowerCase());
assert.equal(keccak256(v.router_calldata), v.approval.calldataHash);
assert.equal(keccak256(readFileSync("fixtures/eip712_golden/manifest.canonical.json")), v.approval.evidenceRoot);
console.log("PASS Python ↔ TypeScript EIP-712 digest, signer, calldata hash and canonical manifest hash");
