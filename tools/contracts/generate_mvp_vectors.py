"""Offline hash vectors. No keys, signing, RPC or mutable fixture regeneration at runtime."""

import json

from eth_abi import encode
from web3 import Web3

from treasury_backend.paths import ROOT
from treasury_contracts.v3 import (
    OPERATION_FIELDS,
    Constraints,
    Operation,
    call_hash,
    operation_digest,
)


def main():
    token = "0x" + "11" * 20
    payee = "0x" + "22" * 20
    treasury = "0x" + "33" * 20
    data = Web3.to_hex(
        Web3.keccak(text="transfer(address,uint256)")[:4]
        + encode(["address", "uint256"], [payee, 1000000])
    )
    phi = Constraints(
        before_balances=("10000000", "0", "0", "0"),
        min_deltas=("-1000000", "0", "0", "0"),
        receipt_credit="1000000",
        max_wavax_balance="0",
    )
    operation = Operation(
        kind=2,
        rebalance=False,
        policyHash="0x" + "01" * 32,
        sessionId="0x" + "02" * 32,
        intentHash="0x" + "03" * 32,
        evidenceRoot="0x" + "04" * 32,
        proofContextHash="0x" + "05" * 32,
        constraintsHash=phi.hash,
        calldataHash=call_hash(token, 0, data),
        target=token,
        tokenIn=token,
        tokenOut=token,
        recipient=payee,
        amount="1000000",
        minOutput="1000000",
        spendDebitUsdE8="101000000",
        riskDebitUsdE8="0",
        nonce="7",
        deadline="2000000030",
    )
    result = {
        "label": "TEST_VECTOR_ONLY",
        "chain_id": 43113,
        "treasury": treasury,
        "operation": operation.model_dump(mode="json"),
        "fields": [{"name": n, "type": t} for n, t in OPERATION_FIELDS],
        "phi": phi.model_dump(mode="json"),
        "phi_abi": "0x" + encode(["(uint256[4],int256[4],uint256,uint256)"], [phi.abi_tuple]).hex(),
        "phi_hash": phi.hash,
        "typed_data_hash": operation_digest(43113, treasury, operation),
        "call_data": data,
    }
    path = ROOT / "fixtures/mvp/hash-vector.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Generated offline MVP ABI/EIP-712 test vector; no keys or transactions")


if __name__ == "__main__":
    main()
