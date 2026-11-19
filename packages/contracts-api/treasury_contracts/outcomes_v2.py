"""V2 receipt checks shared by the observer and execution module; read-only."""

import json
import warnings

from eth_account import Account
from web3 import Web3

from .models import SignedPDR
from .v2 import ApprovalV2, DomainV2, SignedPDRV2, digest_v2, keccak, message_v2


def parse_pdr(value):
    if isinstance(value, str):
        value = json.loads(value)
    cls = SignedPDRV2 if value.get("domain", {}).get("version") == "2" else SignedPDR
    return cls.model_validate(value)


def binding(built, pdr, evidence_root, attestor):
    expected = ApprovalV2(
        intentHash=keccak(built.intent_id.encode()),
        calldataHash=built.calldata_hash,
        policyHash=built.policy_hash,
        evidenceRoot=evidence_root or pdr.approval.evidenceRoot,
        proofContextHash=pdr.approval.proofContextHash,
        postConditionsHash=pdr.phi.hash,
        sessionId=pdr.approval.sessionId,
        riskDebitUsdE8=pdr.approval.riskDebitUsdE8,
        nonce=built.nonce,
        deadline=str(built.deadline),
        adapter=built.router,
        tokenIn=built.token_in,
        tokenOut=built.token_out,
        amountIn=built.amount_in_base_units,
        minAmountOut=built.min_amount_out_base_units,
    )
    domain = DomainV2(chainId=built.chain_id, verifyingContract=built.vault_address)
    problems = []
    if (
        pdr.build_id != built.build_id
        or pdr.domain != domain
        or pdr.approval != expected
        or digest_v2(pdr.domain, pdr.approval) != pdr.typed_data_hash
    ):
        problems.append("PDR_BINDING_MISMATCH")
    if (
        attestor
        and Account.recover_message(
            message_v2(pdr.domain, pdr.approval), signature=pdr.signature
        ).lower()
        != attestor.lower()
    ):
        problems.append("PDR_SIGNER_MISMATCH")
    return problems


def proof_effects(w3, vault, built, pdr, receipt, facts):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        events = vault.events.ProofCommitted().process_receipt(receipt)
    events = [e for e in events if e["address"].lower() == built.vault_address.lower()]
    if not receipt.status:
        return ["REVERTED_RECEIPT_HAS_EFFECTS"] if events else []
    if len(events) != 1:
        return ["PROOF_EVENT_MISMATCH"]
    a = events[0]["args"]
    usdc = vault.functions.usdc().call(block_identifier=receipt.blockNumber).lower()
    di, do = (
        (a["usdcDelta"], a["wavaxDelta"])
        if built.token_in.lower() == usdc
        else (a["wavaxDelta"], a["usdcDelta"])
    )
    if (
        a["nonce"] != int(built.nonce)
        or Web3.to_hex(a["sessionId"]) != pdr.approval.sessionId
        or Web3.to_hex(a["proofContextHash"]) != pdr.approval.proofContextHash
        or Web3.to_hex(a["postConditionsHash"]) != pdr.phi.hash
        or a["riskDebitUsdE8"] != int(pdr.approval.riskDebitUsdE8)
        or di != int(facts["token_in_delta_base_units"])
        or do != int(facts["token_out_delta_base_units"])
    ):
        return ["PROOF_EVENT_MISMATCH"]
    session = vault.functions.sessions(pdr.approval.sessionId).call(
        block_identifier=receipt.blockNumber
    )
    if Web3.to_hex(session[0]) != built.policy_hash or session[4] < int(
        pdr.approval.riskDebitUsdE8
    ):
        return ["PROOF_SESSION_MISMATCH"]
    return []
