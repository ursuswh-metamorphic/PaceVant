from eth_account import Account
from web3 import Web3
from .crypto import canonical, content_hash, digest, keccak, message
from .models import Approval, Domain
from .settings import ROOT


def generate():
    # Published key 0x1234 is ONLY a signature test vector, never configured on Fuji.
    account = Account.from_key((0x1234).to_bytes(32, "big"))
    domain = Domain(
        name="TreasuryPolicyVault",
        version="1",
        chainId=43113,
        verifyingContract="0x1111111111111111111111111111111111111111",
    )
    from eth_abi import encode

    data = Web3.keccak(text="exactInput(address,address,uint256,uint256,address)")[
        :4
    ] + encode(
        ["address", "address", "uint256", "uint256", "address"],
        [
            "0x3333333333333333333333333333333333333333",
            "0x4444444444444444444444444444444444444444",
            500000000,
            24750000000000000000,
            domain.verifyingContract,
        ],
    )
    manifest = {
        "chain_id": 43113,
        "vault_address": domain.verifyingContract,
        "policy_hash": keccak(b"owner-authorized-golden-policy"),
        "calldata_hash": keccak(data),
        "fork_block": 12345678,
        "bytecode_hash": keccak(b"GOLDEN_FIXTURE_NOT_REAL_SIM"),
        "scenario_artifacts": [],
        "parser_version": "extractor-v1",
        "verification_status": "INCOMPLETE",
        "source": "MOCK_FIXTURE",
        "unicode_test": "Việt Nam",
    }
    a = Approval(
        policyHash=manifest["policy_hash"],
        evidenceRoot=content_hash(manifest),
        router="0x2222222222222222222222222222222222222222",
        tokenIn="0x3333333333333333333333333333333333333333",
        tokenOut="0x4444444444444444444444444444444444444444",
        amountIn="500000000",
        minAmountOut="24750000000000000000",
        calldataHash=keccak(data),
        nonce="1001",
        deadline="1799990000",
    )
    path = ROOT / "fixtures/eip712_golden"
    path.mkdir(parents=True, exist_ok=True)
    vector = {
        "source": "MOCK_FIXTURE",
        "test_private_key": "0x" + (0x1234).to_bytes(32, "big").hex(),
        "signer": account.address,
        "domain": domain.model_dump(),
        "approval": a.model_dump(),
        "typed_data_hash": digest(domain, a),
        "router_calldata": Web3.to_hex(data),
        "signature": Web3.to_hex(
            Account.sign_message(message(domain, a), account.key).signature
        ),
    }
    (path / "vector.json").write_bytes(canonical(vector))
    (path / "manifest.json").write_bytes(canonical(manifest))
    (path / "manifest.canonical.json").write_bytes(canonical(manifest))
    (path / "manifest.keccak.txt").write_text(
        content_hash(manifest) + "\n", encoding="utf-8"
    )
