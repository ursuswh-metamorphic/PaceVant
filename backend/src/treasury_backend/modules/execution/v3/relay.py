"""Durable fixed-operation relay; public Fuji requires the explicit MVP activation gate."""

from eth_account import Account
from web3 import Web3
from web3.exceptions import TransactionNotFound

from treasury_contracts.crypto import canonical, content_hash
from treasury_contracts.v3 import Constraints, Operation, operation_message


def observe(service, stage, check_id, status, **values):
    callback = getattr(service, "on_activity", None)
    if callback:
        callback(stage, check_id, status, **values)


def relay(service, build, operation, phi, signature):
    chain, store = service.chain, service.store
    chain.isolated()
    w3 = chain.w3
    account = Account.from_key(chain.settings.relayer_private_key.get_secret_value())
    if account.address.lower() != chain.manifest.relayer or account.address.lower() == chain.manifest.owner:
        raise ValueError("RELAYER_IDENTITY_MISMATCH")
    if Account.recover_message(operation_message(chain.manifest.chain_id, chain.vault.address, operation), signature=signature).lower() != chain.manifest.attestor:
        raise ValueError("BAD_SIGNATURE")
    observe(service, "RELAY", "RELAYER_AUTHORITY", "PASS", expected={"attestor": chain.manifest.attestor, "relayer": chain.manifest.relayer},
            observed={"attestor": chain.manifest.attestor, "relayer": account.address.lower(), "owner_separate": account.address.lower() != chain.manifest.owner})
    payload = {"operation": operation.model_dump(mode="json"), "phi": phi.model_dump(mode="json"), "signature": signature}
    request_hash = content_hash(payload)
    # Reuse the existing execution submission journal, with a separate V3 build namespace.
    with store.db() as db:
        row = db.execute("SELECT request_hash,tx_hash,raw_tx FROM submissions WHERE build_id=?", (build["build_id"],)).fetchone()
    if row:
        if row[0] != request_hash:
            raise ValueError("NONCE_REPLAY")
        observe(service, "RELAY", "IDEMPOTENT_SUBMISSION", "PASS", observed={"tx_hash": row[1], "reused": True, "new_broadcast": False})
        # Recovery is read-only: never replace or invent a second signature after RPC uncertainty.
        return reconcile(service, row[1])
    fn = chain.vault.functions.executeOperation(operation.abi_tuple, phi.abi_tuple, signature)
    from treasury_backend.modules.gas_credit.system import SystemGasLedger,gas_terms
    gas_ledger=SystemGasLedger(store.db_path,chain.settings)
    observe(service, "RELAY", "GAS_GUARD", "RUNNING")
    estimated=fn.estimate_gas({"from":account.address})
    gas,price,max_cost=gas_terms(chain.settings,w3,account.address,estimated)
    observe(service, "RELAY", "GAS_GUARD", "PASS", observed={"gas_limit": gas, "gas_price_wei": str(price), "maximum_next_fee_wei": str(max_cost)},
            expected={"max_tx_fee_wei": str(chain.settings.max_tx_fee_wei), "max_gas_price_wei": str(chain.settings.max_gas_price_wei)})
    tx = fn.build_transaction({"from": account.address, "chainId": w3.eth.chain_id,
                               "nonce": w3.eth.get_transaction_count(account.address, "pending"),
                               "gas":gas,"gasPrice":price})
    signed = account.sign_transaction(tx)
    tx_hash = Web3.to_hex(signed.hash)
    store.put("v3-submitted", tx_hash, {"build_id": build["build_id"], "payload": payload,
                                        "calldata": tx["data"],"relayer_nonce":tx["nonce"]})
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        gas_ledger.reserve(db,tx_hash,chain.manifest.chain_id,account.address,w3.eth.get_block("latest").timestamp//86400,max_cost)
        db.execute("INSERT INTO submissions VALUES(?,?,?,?,?)",
                   (build["build_id"], request_hash, tx_hash, Web3.to_hex(signed.raw_transaction), canonical({"version": 3}).decode()))
    observe(service, "RELAY", "JOURNAL_RESERVED", "PASS", observed={"tx_hash": tx_hash, "request_hash": request_hash, "relayer_nonce": tx["nonce"], "maximum_next_fee_wei": str(max_cost), "atomic_reservation": True})
    try:
        observe(service, "RELAY", "BROADCAST", "RUNNING", observed={"tx_hash": tx_hash})
        w3.eth.send_raw_transaction(signed.raw_transaction)
        observe(service, "RELAY", "BROADCAST", "PASS", observed={"tx_hash": tx_hash, "submitted": True})
        w3.eth.wait_for_transaction_receipt(tx_hash, timeout=chain.settings.receipt_timeout)
    except Exception:
        observe(service, "RELAY", "BROADCAST_RESULT", "UNKNOWN", observed={"tx_hash": tx_hash, "reason_code": "SUBMITTED_UNKNOWN"})
        return {"tx_hash": tx_hash, "status": "SUBMITTED_UNKNOWN", "environment": chain.manifest.environment,
                "public_chain_receipt": False}
    return reconcile(service, tx_hash)


def reconcile(service, tx_hash):
    chain, store = service.chain, service.store
    chain.isolated()
    record = store.get("v3-submitted", tx_hash)
    observe(service, "RECONCILIATION", "RECEIPT_LOOKUP", "RUNNING", observed={"tx_hash": tx_hash})
    from treasury_backend.modules.gas_credit.system import SystemGasLedger
    expense=SystemGasLedger(store.db_path,chain.settings).reconcile(chain.w3,tx_hash)
    try:
        receipt = chain.w3.eth.get_transaction_receipt(tx_hash)
    except TransactionNotFound:
        with store.db() as db:
            observed=db.execute("SELECT 1 FROM records WHERE kind='v3-observed-receipt' AND id=?",(tx_hash,)).fetchone()
        status="REORGED" if observed else "SUBMITTED_UNKNOWN"
        if not observed and "relayer_nonce" in record and chain.w3.eth.get_transaction_count(Web3.to_checksum_address(chain.manifest.relayer))>record["relayer_nonce"]:
            status="REPLACED_UNVERIFIED"
        observe(service, "RECONCILIATION", "RECEIPT_LOOKUP", "UNKNOWN", observed={"tx_hash": tx_hash, "status": status})
        return {"tx_hash": tx_hash, "status": status,"environment":chain.manifest.environment,"public_chain_receipt": False}
    if chain.w3.eth.get_block(receipt.blockNumber).hash != receipt.blockHash:
        observe(service, "RECONCILIATION", "CANONICAL_BLOCK", "UNKNOWN", observed={"status": "REORGED"})
        return {"tx_hash": tx_hash, "status": "REORGED", "public_chain_receipt": False}
    confirmations = chain.w3.eth.block_number - receipt.blockNumber + 1
    observe(service, "RECONCILIATION", "RECEIPT_LOOKUP", "PASS", observed={"tx_hash": tx_hash, "block_number": receipt.blockNumber, "block_hash": Web3.to_hex(receipt.blockHash), "confirmations": confirmations})
    with store.db() as db:
        observed=db.execute("SELECT 1 FROM records WHERE kind='v3-observed-receipt' AND id=?",(tx_hash,)).fetchone()
    if not observed:
        store.put("v3-observed-receipt",tx_hash,{"block_hash":Web3.to_hex(receipt.blockHash),"block_number":receipt.blockNumber})
    result = {"tx_hash": tx_hash, "block_number": receipt.blockNumber, "block_hash": Web3.to_hex(receipt.blockHash),
              "gas_used": str(receipt.gasUsed), "confirmations": confirmations,
              "environment": chain.manifest.environment, "public_chain_receipt": chain.manifest.environment=="REAL_FUJI_EXECUTION",
              "system_gas_expense":expense}
    if receipt.status != 1:
        observe(service, "RECONCILIATION", "VAULT_EXECUTION", "FAIL", expected="SUCCESS", observed="REVERTED")
        return result | {"status": "REVERTED"}
    tx = chain.w3.eth.get_transaction(tx_hash)
    if (tx["to"].lower() != chain.manifest.treasury or tx["from"].lower() != chain.manifest.relayer
            or Web3.to_hex(tx["input"]) != record["calldata"] or tx["value"] != 0):
        raise ValueError("RECEIPT_TRANSACTION_MISMATCH")
    observe(service, "RECONCILIATION", "RECEIPT_BINDINGS", "PASS", observed={"treasury": tx["to"].lower(), "relayer": tx["from"].lower(), "exact_calldata": True, "value": str(tx["value"])})
    operation = Operation.model_validate(record["payload"]["operation"])
    phi = Constraints.model_validate(record["payload"]["phi"])
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        events = chain.vault.events.OperationExecuted().process_receipt(receipt)
    if len(events) != 1 or events[0]["address"].lower()!=chain.manifest.treasury:
        raise ValueError("RECEIPT_EVENT_MISMATCH")
    event = events[0]["args"]
    if (event["nonce"] != int(operation.nonce) or event["kind"] != operation.kind
            or Web3.to_hex(event["sessionId"]) != operation.sessionId
            or Web3.to_hex(event["evidenceRoot"]) != operation.evidenceRoot
            or Web3.to_hex(event["proofContextHash"]) != operation.proofContextHash
            or any(d < int(bound) for d, bound in zip(event["deltas"], phi.min_deltas, strict=True))
            or event["received"] < int(phi.receipt_credit)):
        raise ValueError("RECEIPT_EFFECT_MISMATCH")
    # Check the block again after processing its logs.
    if chain.w3.eth.get_block(receipt.blockNumber).hash != receipt.blockHash:
        observe(service, "RECONCILIATION", "CANONICAL_BLOCK", "UNKNOWN", observed={"status": "REORGED"})
        return result | {"status": "REORGED"}
    observe(service, "RECONCILIATION", "VAULT_EFFECTS", "PASS", expected={"min_deltas": phi.min_deltas, "receipt_credit": phi.receipt_credit, "nonce": operation.nonce, "evidence_root": operation.evidenceRoot, "proof_hash": operation.proofContextHash},
            observed={"actual_deltas": [str(v) for v in event["deltas"]], "payee_received": str(event["received"]), "nonce": str(event["nonce"]), "evidence_root": Web3.to_hex(event["evidenceRoot"]), "proof_hash": Web3.to_hex(event["proofContextHash"])})
    observe(service, "RECONCILIATION", "GAS_SETTLEMENT", "PASS" if (expense or {}).get("actual_cost_wei") is not None else "UNKNOWN", observed=expense)
    observe(service, "RECONCILIATION", "CONFIRMATIONS", "PASS" if confirmations >= chain.settings.required_confirmations else "UNKNOWN",
            expected=chain.settings.required_confirmations, observed=confirmations)
    return result | {"status": "CONFIRMED" if confirmations >= chain.settings.required_confirmations else "PENDING_CONFIRMATIONS",
                     "actual_deltas": [str(v) for v in event["deltas"]], "payee_received": str(event["received"])}
