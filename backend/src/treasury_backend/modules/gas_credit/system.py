"""System-paid relayer expense reservations. No customer, credit, refill or billing concept."""

import sqlite3

from web3 import Web3
from web3.exceptions import TransactionNotFound

from treasury_backend.core.errors import ControlError

SCHEMA = """
CREATE TABLE IF NOT EXISTS system_gas_expenses(
 tx_hash TEXT PRIMARY KEY, chain_id INTEGER NOT NULL, relayer TEXT NOT NULL, utc_day INTEGER NOT NULL,
 max_cost_wei TEXT NOT NULL, actual_cost_wei TEXT NOT NULL, state TEXT NOT NULL,
 block_number INTEGER, block_hash TEXT);
CREATE INDEX IF NOT EXISTS system_gas_scope ON system_gas_expenses(chain_id,relayer,utc_day);
"""


def gas_terms(settings, w3, address, estimated):
    gas = estimated * 12 // 10 + 10000
    price = w3.eth.gas_price
    cost = gas * price
    if gas > settings.max_gas_per_tx:
        raise ControlError("RELAYER_GAS_LIMIT", 409)
    if price > settings.max_gas_price_wei or cost > settings.max_tx_fee_wei:
        raise ControlError("RELAYER_FEE_LIMIT", 409)
    if w3.eth.get_balance(address, "pending") < cost:
        raise ControlError("RELAYER_INSUFFICIENT_AVAX", 409)
    return gas, price, cost


class SystemGasLedger:
    def __init__(self, path, settings):
        self.path, self.settings = path, settings
        with sqlite3.connect(path, timeout=30) as db:
            db.executescript(SCHEMA)

    def reserve(self, db, tx_hash, chain_id, relayer, day, max_cost):
        rows = db.execute(
            "SELECT max_cost_wei,actual_cost_wei,state,utc_day FROM system_gas_expenses WHERE chain_id=? AND relayer=?",
            (chain_id, relayer.lower()),
        ).fetchall()
        used = sum(
            int(r[0]) if r[2] == "HELD" else int(r[1]) if r[3] == day and r[2] == "SETTLED" else 0
            for r in rows
        )
        if used + max_cost > self.settings.max_daily_gas_expense_wei:
            raise ControlError("RELAYER_DAILY_GAS_LIMIT", 409)
        db.execute(
            "INSERT INTO system_gas_expenses VALUES(?,?,?,?,?,'0','HELD',NULL,NULL)",
            (tx_hash, chain_id, relayer.lower(), day, str(max_cost)),
        )

    def reconcile(self, w3, tx_hash):
        with sqlite3.connect(self.path, timeout=30) as db:
            row = db.execute(
                "SELECT chain_id,relayer,max_cost_wei FROM system_gas_expenses WHERE tx_hash=?",
                (tx_hash,),
            ).fetchone()
            if not row:
                return None
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                header = w3.eth.get_block(receipt.blockNumber)
                tx = w3.eth.get_transaction(tx_hash)
                if (
                    w3.eth.chain_id != row[0]
                    or tx["from"].lower() != row[1]
                    or receipt.blockHash != header.hash
                    or w3.eth.block_number - receipt.blockNumber + 1
                    < self.settings.required_confirmations
                ):
                    raise TransactionNotFound("Unverified canonical receipt")
                cost = receipt.gasUsed * receipt.effectiveGasPrice
                if cost > int(row[2]):
                    raise ControlError("RELAYER_FEE_ACCOUNTING_MISMATCH", 409)
                db.execute(
                    "UPDATE system_gas_expenses SET state='SETTLED',actual_cost_wei=?,utc_day=?,block_number=?,block_hash=? WHERE tx_hash=?",
                    (
                        str(cost),
                        header.timestamp // 86400,
                        receipt.blockNumber,
                        Web3.to_hex(receipt.blockHash),
                        tx_hash,
                    ),
                )
                return {
                    "payer": "SYSTEM_RELAYER",
                    "gas_used": str(receipt.gasUsed),
                    "effective_gas_price_wei": str(receipt.effectiveGasPrice),
                    "actual_cost_wei": str(cost),
                    "transaction_status": receipt.status,
                    "billing": False,
                }
            except TransactionNotFound:
                db.execute(
                    "UPDATE system_gas_expenses SET state='HELD',actual_cost_wei='0',block_number=NULL,block_hash=NULL WHERE tx_hash=?",
                    (tx_hash,),
                )
                return None

    def history(self):
        with sqlite3.connect(self.path, timeout=30) as db:
            db.row_factory = sqlite3.Row
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM system_gas_expenses ORDER BY rowid DESC LIMIT 100"
                )
            ]

    def reserved_or_spent(self, chain_id, relayer, day):
        with sqlite3.connect(self.path, timeout=30) as db:
            rows = db.execute(
                "SELECT max_cost_wei,actual_cost_wei,state,utc_day FROM system_gas_expenses WHERE chain_id=? AND relayer=?",
                (chain_id, relayer.lower()),
            ).fetchall()
        return sum(
            int(r[0]) if r[2] == "HELD" else int(r[1]) if r[2] == "SETTLED" and r[3] == day else 0
            for r in rows
        )
