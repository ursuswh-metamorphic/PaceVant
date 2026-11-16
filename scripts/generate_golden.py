import json
import sys
from pathlib import Path

import rfc8785
from eth_keys import keys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps" / "control-plane"), str(ROOT / "packages" / "contracts-api")]

# Public fixture key, used exclusively for a reproducible offline vector.
TEST_KEY = bytes.fromhex("00" * 31 + "02")


def generate():
    from app.attestor.typed import approval_for, digest, hash_bytes, sign_digest, typed_data
    from treasury_contract.wire import BuiltTransaction, Domain, SignedPDR

    calldata = bytes.fromhex("aabbccdd01020304")
    vault = "0x" + "11" * 20
    router, token_in, token_out = ("0x" + byte * 20 for byte in ("22", "33", "44"))
    build = BuiltTransaction(
        build_id="build_golden",
        intent_id="intent_golden",
        chain_id=43113,
        vault_address=vault,
        router=router,
        token_in=token_in,
        token_out=token_out,
        amount_in_base_units="500000000",
        min_amount_out_base_units="24750000000000000000",
        router_calldata="0x" + calldata.hex(),
        calldata_hash=hash_bytes(calldata),
        policy_hash="0x" + "a1" * 32,
        nonce="1001",
        deadline=2000000030,
        quote_ref="quote_golden",
        adapter_version="mock-swap-v1",
    )
    ref = "artifact://simulation/build_golden/report.json"
    baseline = {
        "execution_status": "SUCCESS",
        "token_in_delta_base_units": "-500000000",
        "token_out_delta_base_units": "25000000000000000000",
        "unexpected_transfer": False,
        "unauthorized_approval": False,
        "gas_used": "210000",
    }
    stress_tests = [
        {
            "scenario_id": "reserve_shift_mild",
            "status": "SUCCESS_SAFE",
            "output_base_units": "24950000000000000000",
        },
        {
            "scenario_id": "reserve_shift_adverse",
            "status": "PROTECTED_REVERT",
            "revert_reason": "MIN_OUTPUT_NOT_MET",
        },
    ]
    report = {
        "intent_id": build.intent_id,
        "build_id": build.build_id,
        "nonce": build.nonce,
        "deadline": build.deadline,
        "simulation_mode": "MOCK",
        "source": "MOCK_FIXTURE",
        "baseline": baseline,
        "stress_tests": stress_tests,
    }
    manifest = {
        "chain_id": 43113,
        "vault_address": vault,
        "policy_hash": build.policy_hash,
        "calldata_hash": build.calldata_hash,
        "fork_block": 12345678,
        "fork_block_hash": "0x" + "f1" * 32,
        "fork_block_timestamp": 2000000000,
        "bytecode_hash": "0x" + "b1" * 32,
        "parser_version": "extractor-v1",
        "verification_status": "COMPLETE",
        "artifact_hashes": {ref: hash_bytes(rfc8785.dumps(report))},
    }
    evidence = {
        "schema_version": "1.1",
        **report,
        **{
            key: manifest[key]
            for key in (
                "chain_id",
                "vault_address",
                "policy_hash",
                "calldata_hash",
                "fork_block",
                "bytecode_hash",
                "parser_version",
                "verification_status",
            )
        },
        "artifact_refs": [ref],
        "evidence_manifest_ref": "artifact://simulation/build_golden/manifest.json",
        "evidence_root": hash_bytes(rfc8785.dumps(manifest)),
    }
    domain = Domain(verifyingContract=vault)
    approval = approval_for(build, evidence["evidence_root"])
    message_hash = digest(domain, approval)
    key = keys.PrivateKey(TEST_KEY)
    pdr = SignedPDR(
        decision_id="decision_golden",
        build_id=build.build_id,
        domain=domain,
        approval=approval,
        typed_data_hash="0x" + message_hash.hex(),
        signature=sign_digest(key, message_hash),
    )
    return (
        {
            "built_transaction": build.model_dump(),
            "signed_pdr": pdr.model_dump(),
            "signer": key.public_key.to_address(),
            "typed_data": typed_data(domain, approval),
            "simulation_evidence": evidence,
        },
        manifest,
        report,
    )


if __name__ == "__main__":
    vector, manifest, report = generate()
    target = ROOT / "fixtures" / "eip712_golden"
    target.mkdir(exist_ok=True)
    for name, data in (("vector.json", vector), ("manifest.json", manifest)):
        (target / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (target / "manifest.jcs").write_bytes(rfc8785.dumps(manifest))
    (target / "report.json").write_bytes(rfc8785.dumps(report))
