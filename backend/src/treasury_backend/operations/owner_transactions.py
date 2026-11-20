"""Journal owner transactions before broadcast; resume the same signed bytes on retry."""

import json
import re

from eth_account import Account
from filelock import FileLock
from web3 import Web3
from web3.exceptions import TransactionNotFound

from .env import atomic_json
from .errors import OpsError


def send_owner_transaction(p, w3, account, scope, step, build):
    if not re.fullmatch(r"[0-9a-f]{64}", scope) or not re.fullmatch(r"[a-z-]{1,40}", step):
        raise OpsError("Invalid owner transaction journal scope")
    path = p.control_data / "owner-renewals" / scope / (step + ".json")
    p.control_data.mkdir(parents=True, exist_ok=True)
    with FileLock(str(p.control_data / "owner-send.lock"), timeout=5):
        if w3.eth.chain_id != p.chain_id:
            raise OpsError("Owner transaction RPC chain mismatch")
        if path.exists():
            journal = json.loads(path.read_text(encoding="utf-8"))
        else:
            tx = build()
            if (
                tx.get("chainId") != p.chain_id
                or tx.get("from", "").lower() != account.address.lower()
            ):
                raise OpsError("Owner transaction sender or chain mismatch")
            signed = account.sign_transaction(tx)
            journal = {
                "schema_version": "owner-transaction-v1",
                "chain_id": p.chain_id,
                "sender": account.address,
                "tx_hash": Web3.to_hex(signed.hash),
                "raw_tx": Web3.to_hex(signed.raw_transaction),
            }
            atomic_json(path, journal)
        raw = Web3.to_bytes(hexstr=journal["raw_tx"])
        if (
            journal["chain_id"] != p.chain_id
            or journal["sender"].lower() != account.address.lower()
            or Web3.to_hex(Web3.keccak(raw)) != journal["tx_hash"]
            or Account.recover_transaction(raw).lower() != account.address.lower()
        ):
            raise OpsError("Owner transaction journal failed integrity verification")
        try:
            try:
                w3.eth.get_transaction(journal["tx_hash"])
            except TransactionNotFound:
                w3.eth.send_raw_transaction(raw)
            receipt = w3.eth.wait_for_transaction_receipt(journal["tx_hash"], timeout=90)
        except Exception:
            raise OpsError(
                "Owner transaction outcome unknown; rerun the same renewal to resume its journal: "
                + journal["tx_hash"]
            ) from None
        if receipt.status != 1:
            raise OpsError("Owner configuration transaction reverted: " + journal["tx_hash"])
        public = {"tx_hash": journal["tx_hash"], "block": receipt.blockNumber}
        atomic_json(path, journal | {"receipt": public})
        return public
