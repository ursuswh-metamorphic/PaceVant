"""One read-only receipt/transaction verifier for A and B; never submits a transaction."""

import time
import warnings

from eth_abi import decode
from web3 import Web3
from web3.exceptions import TransactionNotFound

from .crypto import approval_for, approval_tuple, digest, domain_for, keccak, recover
from .models import ExecutionReconciliation
from .onchain import vault_abi
from .readonly import ReadError
from .token_facts import token_facts


def _address_call(w3, address, signature, block):
    raw = w3.eth.call(
        {"to": Web3.to_checksum_address(address), "data": Web3.keccak(text=signature)[:4]},
        block_identifier=block,
    )
    return Web3.to_checksum_address(decode(["address"], raw)[0])


def verify_outcome(
    w3,
    built,
    pdr,
    tx_hash,
    *,
    expected_relayer,
    expected_attestor=None,
    bytecode_hash=None,
    evidence_root=None,
    now=None,
):
    out = dict(
        chain_id=built.chain_id,
        vault_address=built.vault_address,
        build_id=built.build_id,
        decision_id=pdr.decision_id,
        tx_hash=tx_hash,
        typed_data_hash=pdr.typed_data_hash,
        observed_at=int(time.time()) if now is None else now,
        verification_status="UNAVAILABLE",
        receipt_status="UNKNOWN",
    )
    reasons = []
    try:
        if w3.eth.chain_id != built.chain_id or built.chain_id not in {31337, 43113}:
            raise ReadError("CHAIN_MISMATCH")
        if (
            pdr.build_id != built.build_id
            or digest(pdr.domain, pdr.approval) != pdr.typed_data_hash
            or digest(pdr.domain, pdr.approval)
            != digest(
                domain_for(built), approval_for(built, evidence_root or pdr.approval.evidenceRoot)
            )
        ):
            reasons.append("PDR_BINDING_MISMATCH")
        if (
            expected_attestor
            and recover(pdr.domain, pdr.approval, pdr.signature).lower()
            != expected_attestor.lower()
        ):
            reasons.append("PDR_SIGNER_MISMATCH")
        try:
            tx = w3.eth.get_transaction(tx_hash)
            receipt = w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return ExecutionReconciliation(
                **{
                    **out,
                    "verification_status": "PENDING",
                    "receipt_status": "PENDING",
                    "reason_codes": ["RECEIPT_UNAVAILABLE"],
                }
            )
        header = w3.eth.get_block(receipt.blockNumber)
        head = w3.eth.get_block("latest")
        if (
            Web3.to_hex(receipt.transactionHash) != tx_hash
            or Web3.to_hex(tx.hash) != tx_hash
            or receipt.blockHash != header.hash
            or tx.blockHash != header.hash
            or tx.blockNumber != receipt.blockNumber
            or header.number != receipt.blockNumber
            or receipt.blockNumber > head.number
        ):
            return ExecutionReconciliation(
                **{
                    **out,
                    "verification_status": "REORGED",
                    "reason_codes": ["RECEIPT_NOT_CANONICAL"],
                }
            )
        status = int(receipt.status)
        if status not in {0, 1}:
            raise ReadError("MALFORMED_RECEIPT")
        count = head.number - receipt.blockNumber + 1
        out.update(
            canonical=True,
            block_number=receipt.blockNumber,
            block_hash=Web3.to_hex(header.hash),
            block_timestamp=header.timestamp,
            head_block=head.number,
            confirmations=count,
            finality_confidence="DEPTH_CONFIRMED" if count >= 2 else "INCLUDED",
            receipt_status="SUCCESS" if status else "REVERTED",
        )
        seen_logs = set()
        for log in receipt.logs:
            index=log.get("logIndex")
            if (log.get("removed",False) or log.get("transactionHash")!=receipt.transactionHash
                    or log.get("blockHash")!=header.hash or log.get("blockNumber")!=receipt.blockNumber
                    or not isinstance(index,int) or index in seen_logs):
                reasons.append("LOG_RECEIPT_BINDING_MISMATCH")
            seen_logs.add(index)
        vault = w3.eth.contract(
            address=Web3.to_checksum_address(built.vault_address), abi=vault_abi()
        )
        expected_input = Web3.to_bytes(
            hexstr=vault.encode_abi(
                "executeApprovedSwap",
                args=[approval_tuple(pdr.approval), built.router_calldata, pdr.signature],
            )
        )
        if (
            not tx.get("to")
            or tx.to.lower() != built.vault_address.lower()
            or int(tx.value) != 0
            or bytes(tx.input) != expected_input
            or int(tx.get("chainId", built.chain_id)) != built.chain_id
            or tx["from"].lower() != expected_relayer.lower()
            or receipt["from"].lower() != tx["from"].lower()
            or not receipt.get("to")
            or receipt.to.lower() != built.vault_address.lower()
        ):
            reasons.append("TRANSACTION_BUILD_MISMATCH")
        if (
            bytecode_hash
            and keccak(w3.eth.get_code(vault.address, receipt.blockNumber)) != bytecode_hash
        ):
            reasons.append("VAULT_BYTECODE_MISMATCH")
        gas, price = int(receipt.gasUsed), int(receipt.effectiveGasPrice)
        if gas <= 0 or price < 0 or gas > int(tx.gas):
            reasons.append("MALFORMED_GAS_RECEIPT")
        elif not reasons:
            out.update(
                gas_used=str(gas),
                effective_gas_price_wei=str(price),
                gas_cost_wei=str(gas * price),
                gas_payer=tx["from"],
                gas_verified=True,
                gas_payer_role="RELAYER",
            )
        route = None
        if built.adapter_version == "lfj-v1-fuji-v1":
            actual_router = _address_call(w3, built.router, "lfjRouter()", receipt.blockNumber)
            pair = _address_call(w3, built.router, "pair()", receipt.blockNumber)
            authorized = _address_call(w3, built.router, "authorizedVault()", receipt.blockNumber)
            if (
                built.chain_id != 43113
                or authorized.lower() != built.vault_address.lower()
                or actual_router.lower() != "0x18556da13313f3532c54711497a8fedac273220e"
            ):
                reasons.append("EXECUTION_ROUTE_MISMATCH")
            route = {"lfj_router": actual_router, "pair": pair}
        facts = token_facts(
            receipt,
            built.vault_address,
            built.router,
            built.token_in,
            built.token_out,
            int(built.amount_in_base_units),
            int(built.min_amount_out_base_units),
            route,
        )
        out.update(
            token_in_delta_base_units=facts["token_in_delta_base_units"],
            token_out_delta_base_units=facts["token_out_delta_base_units"],
            transfers=facts["transfers"],
            approvals=facts["approvals"],
            dex_route=route,
        )
        if facts["unexpected_transfer"]:
            reasons.append("UNEXPECTED_TRANSFER")
        if facts["unauthorized_approval"]:
            reasons.append("UNAUTHORIZED_APPROVAL")
        nonce_used = vault.functions.usedNonce(int(built.nonce)).call(
            block_identifier=receipt.blockNumber
        )
        out["nonce_used"] = nonce_used
        # Minimal ERC-20 allowance ABI; token identity comes from the approved build.
        data = Web3.keccak(text="allowance(address,address)")[:4]
        from eth_abi import encode

        def allowance(owner, spender):
            raw = w3.eth.call(
                {
                    "to": Web3.to_checksum_address(built.token_in),
                    "data": data + encode(["address", "address"], [owner, spender]),
                },
                block_identifier=receipt.blockNumber,
            )
            return str(decode(["uint256"], raw)[0])

        out["allowances"] = {"vault_to_adapter": allowance(built.vault_address, built.router)}
        if route:
            out["allowances"]["adapter_to_dex"] = allowance(built.router, route["lfj_router"])
        if any(int(value) != 0 for value in out["allowances"].values()):
            reasons.append("RESIDUAL_ALLOWANCE")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            events = vault.events.SwapExecuted().process_receipt(receipt)
        matching = []
        for e in events:
            a = e["args"]
            event = {
                "nonce": str(a["nonce"]),
                "policy_hash": Web3.to_hex(a["policyHash"]),
                "evidence_root": Web3.to_hex(a["evidenceRoot"]),
                "token_in": a["tokenIn"],
                "token_out": a["tokenOut"],
                "amount_in_base_units": str(a["amountIn"]),
                "amount_out_base_units": str(a["amountOut"]),
                "log_index": e["logIndex"],
            }
            if e["address"].lower() == built.vault_address.lower():
                matching.append(event)
        out["swap_events"] = matching
        if status:
            if (facts["token_in_delta_base_units"] != f"-{built.amount_in_base_units}"
                or int(facts["token_out_delta_base_units"]) < int(built.min_amount_out_base_units)):
                reasons.append("TOKEN_DELTA_MISMATCH")
            if not nonce_used:
                reasons.append("NONCE_NOT_CONSUMED")
            event_bad = len(matching) != 1
            if not event_bad:
                event = matching[0]
                event_bad = any(
                    [
                        event["nonce"] != built.nonce,
                        event["policy_hash"] != built.policy_hash,
                        event["evidence_root"] != pdr.approval.evidenceRoot,
                        event["token_in"].lower() != built.token_in.lower(),
                        event["token_out"].lower() != built.token_out.lower(),
                        event["amount_in_base_units"] != built.amount_in_base_units,
                        event["amount_out_base_units"] != facts["token_out_delta_base_units"],
                    ]
                )
            if event_bad:
                reasons.append("SWAP_EVENT_MISMATCH")
        elif matching or facts["transfers"] or facts["approvals"]:
            reasons.append("REVERTED_RECEIPT_HAS_EFFECTS")
        if w3.eth.get_block(receipt.blockNumber).hash != header.hash:
            out.update(
                canonical=False,
                gas_verified=False,
                verification_status="REORGED",
                reason_codes=["RECEIPT_CHANGED_DURING_READ"],
            )
        else:
            out.update(
                verification_status="MISMATCH" if reasons else "VERIFIED",
                reason_codes=list(dict.fromkeys(reasons)),
            )
        return ExecutionReconciliation(**out)
    except ReadError as error:
        return ExecutionReconciliation(
            **{
                **out,
                "verification_status": "UNAVAILABLE",
                "gas_verified": False,
                "reason_codes": [error.code],
            }
        )
    except Exception:
        # No exception details, signed calldata or provider internals are exposed.
        return ExecutionReconciliation(
            **{
                **out,
                "verification_status": "UNAVAILABLE",
                "gas_verified": False,
                "reason_codes": ["OUTCOME_RPC_OR_DATA_UNAVAILABLE"],
            }
        )
