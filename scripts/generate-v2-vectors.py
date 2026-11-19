"""Regenerate deterministic, public TEST_ONLY ABI vectors. No environment keys."""

import json
import runpy
from pathlib import Path

from eth_abi import encode
from eth_account import Account

from treasury_contracts.proof import PGSProofEngine
from treasury_contracts.v2 import APPROVAL_V2_FIELDS, DomainV2, approval_v2, digest_v2, message_v2

ROOT = Path(__file__).resolve().parents[1]
args = runpy.run_path(str(ROOT / "tests/integration/test_proof_v2.py"))["case"]()
b, e, p, r, o, s, now = args
proof = PGSProofEngine().prove(*args)
assert proof.status == "VERIFIED"
approval = approval_v2(b, e.hash, proof, s.session_id)
domain = DomainV2(chainId=b.chain_id, verifyingContract=b.vault_address)
# Public deterministic fixture key, never deployed or loaded by production configuration.
key = (0x1234).to_bytes(32, "big")
signature = Account.sign_message(message_v2(domain, approval), key).signature.hex()
values = tuple(
    bytes.fromhex(v[2:]) if kind == "bytes32" else v
    for v, (_, kind) in zip(approval.abi_tuple, APPROVAL_V2_FIELDS, strict=True)
)
vector = {
    "label": "TEST_ONLY",
    "domain": domain.model_dump(),
    "approval": approval.model_dump(),
    "phi": proof.phi.model_dump(mode="json"),
    "phi_abi": "0x" + proof.phi.abi_bytes.hex(),
    "phi_hash": proof.phi.hash,
    "registry_hash": r.hash,
    "policy_config_hash": p.hash,
    "approval_abi": "0x"
    + encode(["(" + ",".join(t for _, t in APPROVAL_V2_FIELDS) + ")"], [values]).hex(),
    "typed_data_hash": digest_v2(domain, approval),
    "signature": "0x" + signature.removeprefix("0x"),
    "signer": Account.from_key(key).address,
    "proof": proof.model_dump(mode="json"),
}
directory = ROOT / "fixtures/v2_1"
directory.mkdir(exist_ok=True)
(directory / "golden.json").write_text(json.dumps(vector, indent=2) + "\n", encoding="utf-8")
(directory / "TEST_ONLY_policy.json").write_text(
    json.dumps(
        {
            "proof_policy": p.model_dump(mode="json"),
            "session_limit_usd_e8": "1000000000",
            "session_duration_seconds": 3600,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("V2 ABI/EIP-712 vectors generated")
