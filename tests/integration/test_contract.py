import json
from pathlib import Path

import httpx
import pytest
import rfc8785
from jsonschema import Draft202012Validator

from app.attestor.typed import digest, hash_bytes, recover_signer, typed_data
from app.errors import ControlError
from app.orchestration.fuji import FUJI_RPC, FujiVerifier
from app.orchestration.mock import MockExecutionClient
from app.settings import ROOT
from treasury_contract.wire import BuiltTransaction, SignedPDR, SimulationEvidence

GOLDEN = ROOT / "fixtures" / "eip712_golden"


def test_golden_hashes_and_shared_schemas():
    raw = json.loads((GOLDEN / "vector.json").read_text("utf-8"))
    manifest = json.loads((GOLDEN / "manifest.json").read_text("utf-8"))
    assert rfc8785.dumps(manifest) == (GOLDEN / "manifest.jcs").read_bytes()
    assert next(iter(manifest["artifact_hashes"].values())) == hash_bytes(
        (GOLDEN / "report.json").read_bytes()
    )
    pdr = SignedPDR.model_validate(raw["signed_pdr"])
    evidence = SimulationEvidence.model_validate(raw["simulation_evidence"])
    assert typed_data(pdr.domain, pdr.approval) == raw["typed_data"]
    expected = bytes.fromhex(pdr.typed_data_hash[2:])
    assert digest(pdr.domain, pdr.approval) == expected
    assert recover_signer(expected, pdr.signature) == raw["signer"]
    assert (
        hash_bytes(rfc8785.dumps(manifest)) == pdr.approval.evidenceRoot == evidence.evidence_root
    )
    built = BuiltTransaction.model_validate(raw["built_transaction"])
    assert hash_bytes(bytes.fromhex(built.router_calldata[2:])) == pdr.approval.calldataHash

    schema_path = Path("packages/contracts-api/schemas/v1.1.json")
    schema = json.loads(schema_path.read_text("utf-8"))
    for name, field in [
        ("BuiltTransaction", "built_transaction"),
        ("SignedPDR", "signed_pdr"),
        ("SimulationEvidence", "simulation_evidence"),
    ]:
        Draft202012Validator(
            {
                "$defs": schema["$defs"],
                "$ref": f"#/$defs/{name}",
            }
        ).validate(raw[field])


@pytest.mark.parametrize(
    "result", ["verified", "wrong_chain", "code_drift", "wrong_block", "rpc_error"]
)
def test_fuji_independent_read_only_check(result):
    from app.models import Mandate
    from app.settings import FIXTURES

    now = 2_000_000_000
    m = Mandate.model_validate_json((FIXTURES / "mandate.json").read_bytes())
    backend = MockExecutionClient(
        m,
        "0x" + "aa" * 20,
        {
            "usdc_base_units": "1",
            "wavax_base_units": "1",
        },
        lambda: now,
    )
    code = "0xaabbccdd"
    context = backend.context(fork_block=backend.block).model_copy(
        update={
            "deployment": "FUJI",
            "bytecode_hash": hash_bytes(bytes.fromhex(code[2:])),
        }
    )

    def handler(request):
        assert str(request.url) == FUJI_RPC
        assert "Authorization" not in request.headers
        calls = json.loads(request.content)
        assert all(
            call["method"]
            in {
                "eth_chainId",
                "eth_getBlockByNumber",
                "eth_getCode",
            }
            for call in calls
        )
        if result == "rpc_error":
            return httpx.Response(503)
        block = {
            "number": hex(backend.block),
            "timestamp": hex(now),
            "hash": context.fork_block_hash,
        }
        values = [
            "0xa86a" if result == "wrong_chain" else "0xa869",
            block,
            {**block, "hash": "0x" + "55" * 32} if result == "wrong_block" else block,
            code,
            "0xdead" if result == "code_drift" else code,
        ]
        return httpx.Response(
            200,
            json=[{"id": i, "jsonrpc": "2.0", "result": value} for i, value in enumerate(values)],
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        verifier = FujiVerifier(http)
        if result == "verified":
            verifier.verify(context, now)
        else:
            expected = (
                "FUJI_RPC_UNVERIFIED" if result == "rpc_error" else "FUJI_DEPLOYMENT_MISMATCH"
            )
            with pytest.raises(ControlError, match=expected):
                verifier.verify(context, now)
