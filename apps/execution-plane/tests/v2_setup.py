"""Explicit local-only policy fixture activation; never reads project .env."""

import json
from eth_account import Account
from app.cli import send
from app.crypto import content_hash
from app.settings import ROOT
from treasury_contracts.v2 import ProofPolicy


def activate(chain, keys, tmp_path, policy_changes=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    fixture = json.loads((ROOT / "fixtures/v2_1/TEST_ONLY_policy.json").read_text())
    policy = ProofPolicy.model_validate(fixture["proof_policy"] | (policy_changes or {}))
    owner = Account.from_key(keys["owner"])
    assert chain.chain_id == 31337 and policy.authorization == "TEST_ONLY"
    send(
        chain.w3,
        owner,
        chain.vault.functions.configureProofPolicy(chain.router.address, policy.abi_tuple),
    )
    send(
        chain.w3,
        owner,
        chain.vault.functions.configurePolicy(
            content_hash({"TEST_ONLY": "v2.1"}),
            500 * 10**6,
            1000 * 10**6,
            100,
            chain.w3.eth.get_block("latest").timestamp + 86400,
        ),
    )
    session_id = content_hash({"TEST_ONLY_session": str(tmp_path)})
    now = chain.w3.eth.get_block("latest").timestamp
    send(
        chain.w3,
        owner,
        chain.vault.functions.createSession(
            session_id, now, now + 3600, int(fixture["session_limit_usd_e8"])
        ),
    )
    send(chain.w3, owner, chain.usdc.functions.mint(chain.router.address, 100000 * 10**6))
    chain.deployment = {
        **chain.deployment,
        "pdr_version": "2",
        "session_id": session_id,
        "policy_hash": chain.context()["policy_hash"],
    }
    deployment = tmp_path / "deployment-v2.json"
    deployment.write_text(json.dumps(chain.deployment))
    chain.settings = chain.settings.model_copy(update={"deployment_file": deployment})
    return policy
