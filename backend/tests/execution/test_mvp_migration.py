"""Public-style manifest sealing is read-only and requires an external Owner signature."""
from eth_account import Account
from tools.operations.seal_mvp_manifest import inspect_manifest
from web3 import Web3


def test_mvp_manifest_can_be_inspected_then_owner_signed_without_a_fourth_account(mvp):
    m=mvp["manifest"]
    plan={"chain_id":31337,"predicted_vault":m.treasury,"predicted_adapter":m.adapter,
          "existing_roles":{r:getattr(m,r) for r in ("owner","attestor","relayer")},"session_id":m.default_session_id,
          "config":{"max_daily_execution_cost_usd_e8":m.max_daily_execution_cost_usd_e8}}
    draft=inspect_manifest(mvp["execution"].chain.w3,plan)
    assert draft.owner_signature=="0x"
    signed=draft.model_copy(update={"owner_signature":Web3.to_hex(mvp["owner"].sign_message(draft.signing_message()).signature)})
    signed.verify_owner()
    assert Account.recover_message(signed.signing_message(),signature=signed.owner_signature).lower()==m.owner


def test_owner_renewal_is_unsigned_and_preserves_contracts_and_economic_policy(mvp):
    from tools.operations.prepare_mvp_renewal import prepare

    w3 = mvp["execution"].chain.w3
    vault = mvp["contracts"][0]
    before = vault.functions.activePolicyHash().call()
    cfg = {"session_duration_seconds":604800, "session_swap_usd_e8":"300000000",
           "session_payment_usdc":"5000000", "max_actions":500, "rebalance_cooldown_seconds":60}
    plan = prepare(w3, mvp["manifest"], cfg)
    assert not plan["broadcast"] and not plan["owner_key_accessed"]
    assert len(plan["transactions"]) == 3
    assert plan["predicted_vault"] == mvp["manifest"].treasury
    assert vault.functions.activePolicyHash().call() == before
    assert all(x["owner_signature_required"] for x in plan["transactions"])
