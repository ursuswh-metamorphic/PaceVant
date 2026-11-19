"""Fuji wallet and oracle observations with explicit chain and asset provenance."""

import os
from decimal import Decimal, InvalidOperation

import rfc8785
from eth_abi import decode, encode
from eth_abi.exceptions import DecodingError
from eth_utils import keccak

from app.fuji_oracles import CHAINLINK_FEEDS, chainlink, pyth
from app.fuji_rpc import (
    EXPLORER,
    FUJI_CHAIN_ID,
    FUJI_RPC,
    HASH,
    FujiReadError,
    FujiRPC,
    hex_data,
    quantity,
    require_address,
    timestamp_fields,
)

FUJI_USDC = "0x5425890298aed601595a70AB815c96711a31Bc65"
FUJI_WAVAX = "0xd00ae08403B9bbb9124bB305C09058E32C39A48c"
WITNET_FUJI_ROUTER = "0x1111AbA2164AcdC6D291b08DfB374280035E1111"
AVAX_USD_PAIR = keccak(text="Price-AVAX/USD-6")
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
MAX_ORACLE_AGE_SECONDS = 24 * 60 * 60
WITNET_DOC = (
    "https://docs.witnet.io/smart-contracts/witnet-data-feeds/addresses/avalanche-price-feeds"
)


def observation(provider, address, **fields):
    return {
        "provider": provider,
        "network": "AVALANCHE_FUJI",
        "contract": address,
        "pair": "AVAX/USD",
        "status": "UNAVAILABLE",
        "usable_for_decisions": False,
        "explorer_url": f"{EXPLORER}/address/{address}",
        **fields,
    }


class FujiReader(FujiRPC):
    def token_balance(self, token, holder, expected_decimals, kind):
        out = {
            "symbol": "USDC" if expected_decimals == 6 else "WAVAX",
            "contract": require_address(token),
            "decimals": expected_decimals,
            "kind": kind,
            "status": "UNAVAILABLE",
        }
        try:
            out["bytecode_hash"] = self.code(token)
            (decimals,) = self.eth_call(token, "decimals()", returns=("uint8",))
            if decimals != expected_decimals:
                raise FujiReadError("FUJI_TOKEN_DECIMALS_MISMATCH")
            (balance,) = self.eth_call(
                token,
                "balanceOf(address)",
                ("address",),
                (holder,),
            )
            out.update(status="VERIFIED", balance_base_units=str(balance))
        except FujiReadError as error:
            out["reason_code"] = error.code
        return out

    def oracle(self):
        info = observation(
            "WITNET",
            WITNET_FUJI_ROUTER,
            decimals=6,
            pair_id="0x" + AVAX_USD_PAIR.hex(),
            source_url=WITNET_DOC,
            freshness_limit_seconds=MAX_ORACLE_AGE_SECONDS,
        )
        try:
            info["bytecode_hash"] = self.code(WITNET_FUJI_ROUTER)
            price, updated, status = self.eth_call(
                WITNET_FUJI_ROUTER,
                "valueFor(bytes32)",
                ("bytes32",),
                (AVAX_USD_PAIR,),
                ("int256", "uint256", "uint256"),
            )
            info.update(
                price_raw=str(price),
                oracle_update_status=status,
                **timestamp_fields(self.now, updated),
            )
            if status != 200 or price <= 0 or not 0 < updated <= self.block["timestamp"]:
                info.update(status="UNVERIFIED", reason_code="ORACLE_NO_VALID_UPDATE")
            else:
                info.update(
                    price_usd_e8=str(price * 100),
                    status="WITHIN_HEARTBEAT"
                    if self.now - updated <= MAX_ORACLE_AGE_SECONDS
                    else "STALE",
                )
        except FujiReadError as error:
            info["reason_code"] = error.code
        return info

    def market(self):
        output = {
            "provider": "COINGECKO_DEMO",
            "pair": "AVAX/USD",
            "source_type": "OFFCHAIN_MARKET_API",
            "status": "NOT_CONFIGURED",
            "usable_for_decisions": False,
        }
        key = os.environ.get("PACEVANT_COINGECKO_DEMO_KEY")
        if not key:
            return output
        try:
            payload = self.json_request(
                "GET",
                COINGECKO_URL,
                params={
                    "ids": "avalanche-2",
                    "vs_currencies": "usd",
                    "include_last_updated_at": "true",
                },
                headers={"x-cg-demo-api-key": key, "Accept": "application/json"},
            )
            entry = payload["avalanche-2"]
            price = Decimal(str(entry["usd"]))
            updated = entry["last_updated_at"]
            if (
                not price.is_finite()
                or price <= 0
                or price >= Decimal(10**12)
                or type(updated) is not int
                or not 0 < updated <= self.now
            ):
                raise ValueError("invalid price")
            output.update(
                price_usd_e8=str(int(price * 100_000_000)),
                updated_at=updated,
                age_seconds=self.now - updated,
                status="FRESH" if self.now - updated <= 180 else "STALE",
            )
        except (FujiReadError, ValueError, KeyError, TypeError, InvalidOperation, OverflowError):
            output["status"] = "UNAVAILABLE"
        return output

    def vault(self, address):
        out = {
            "address": address,
            "status": "UNAVAILABLE",
            "explorer_url": f"{EXPLORER}/address/{address}",
        }
        try:
            out["bytecode_hash"] = self.code(address)
            for name, signature, result_type in [
                ("owner", "owner()", "address"),
                ("attestor", "attestor()", "address"),
                ("token_in", "usdc()", "address"),
                ("token_out", "wavax()", "address"),
                ("policy_hash", "activePolicyHash()", "bytes32"),
                ("policy_active", "policyActive()", "bool"),
                ("paused", "paused()", "bool"),
                ("policy_version", "policyVersion()", "uint256"),
                ("policy_expires_at", "policyExpiresAt()", "uint256"),
                ("max_per_swap_base_units", "maxPerSwap()", "uint256"),
                ("max_spend_per_day_base_units", "maxSpendPerDay()", "uint256"),
            ]:
                (value,) = self.eth_call(address, signature, returns=(result_type,))
                if result_type == "bytes32":
                    value = "0x" + value.hex()
                if name.endswith("base_units") or name == "policy_version":
                    value = str(value)
                if name == "policy_expires_at" and value > 253402300799:
                    raise FujiReadError("FUJI_BAD_POLICY_STATE")
                out[name] = value
            utc_day = self.block["timestamp"] // 86400
            (spent,) = self.eth_call(address, "dailySpentUsdc(uint256)", ("uint256",), (utc_day,))
            out.update(
                utc_day=utc_day,
                daily_spent_usdc_base_units=str(spent),
                remaining_daily_usdc_base_units=str(
                    max(0, int(out["max_spend_per_day_base_units"]) - spent)
                ),
                assets=[
                    self.token_balance(out["token_in"], address, 6, "VAULT_CONFIGURED_USDC"),
                    self.token_balance(out["token_out"], address, 18, "VAULT_CONFIGURED_WAVAX"),
                ],
                status="VERIFIED",
                interface_check="POLICY_VAULT_ABI_READS",
                deployment_authenticity="COMPARE_RUNTIME_HASH_WITH_TRUSTED_DEPLOYMENT_MANIFEST",
            )
        except FujiReadError as error:
            out["reason_code"] = error.code
        return out

    def receipt(self, tx_hash, vault_address):
        if not isinstance(tx_hash, str) or not HASH.fullmatch(tx_hash):
            raise FujiReadError("INVALID_TRANSACTION_HASH")
        value = self.rpc("eth_getTransactionReceipt", [tx_hash])
        out = {"tx_hash": tx_hash, "explorer_url": f"{EXPLORER}/tx/{tx_hash}", "status": "PENDING"}
        if value is None:
            return out
        if not isinstance(value, dict) or value.get("transactionHash") != tx_hash:
            raise FujiReadError("FUJI_BAD_RECEIPT")
        block_number = quantity(value.get("blockNumber"), "FUJI_BAD_RECEIPT")
        receipt_hash = value.get("blockHash")
        if not isinstance(receipt_hash, str) or not HASH.fullmatch(receipt_hash):
            raise FujiReadError("FUJI_BAD_RECEIPT")
        receipt_block = self.rpc("eth_getBlockByNumber", [hex(block_number), False])
        if (
            block_number > self.block["number"]
            or not isinstance(receipt_block, dict)
            or receipt_block.get("hash") != receipt_hash
            or quantity(receipt_block.get("number"), "FUJI_BAD_RECEIPT") != block_number
        ):
            raise FujiReadError("FUJI_RECEIPT_NOT_IN_SNAPSHOT")
        gas = quantity(value.get("gasUsed"), "FUJI_BAD_RECEIPT")
        gas_price = quantity(value.get("effectiveGasPrice"), "FUJI_BAD_RECEIPT")
        status = quantity(value.get("status"), "FUJI_BAD_RECEIPT")
        if status not in (0, 1):
            raise FujiReadError("FUJI_BAD_RECEIPT")
        recipient = value.get("to")
        if recipient is not None:
            try:
                recipient = require_address(recipient)
            except FujiReadError:
                raise FujiReadError("FUJI_BAD_RECEIPT") from None
        out.update(
            status="CONFIRMED" if status == 1 else "REVERTED",
            block_number=block_number,
            block_hash=value["blockHash"],
            gas_used=str(gas),
            gas_cost_wei=str(gas * gas_price),
            recipient=recipient,
            vault_match=bool(vault_address and recipient == vault_address),
        )
        events = []
        if out["vault_match"] and status == 1:
            topic = (
                "0x"
                + keccak(
                    text="SwapExecuted(uint256,bytes32,bytes32,address,address,uint256,uint256)"
                ).hex()
            )
            logs = value.get("logs")
            if not isinstance(logs, list):
                raise FujiReadError("FUJI_BAD_RECEIPT")
            for log in logs:
                if not isinstance(log, dict):
                    raise FujiReadError("FUJI_BAD_RECEIPT")
                topics = log.get("topics", [])
                try:
                    log_address = require_address(log.get("address"))
                except FujiReadError:
                    raise FujiReadError("FUJI_BAD_RECEIPT") from None
                if not isinstance(topics, list):
                    raise FujiReadError("FUJI_BAD_RECEIPT")
                if log_address != vault_address or not topics or topics[0] != topic:
                    continue
                try:
                    if len(topics) != 3 or not all(
                        isinstance(t, str) and HASH.fullmatch(t) for t in topics
                    ):
                        raise ValueError("invalid indexed fields")
                    types = ["bytes32", "address", "address", "uint256", "uint256"]
                    raw = hex_data(log["data"])
                    decoded = decode(types, raw)
                    if encode(types, decoded) != raw:
                        raise ValueError("noncanonical event ABI")
                    root, token_in, token_out, amount_in, amount_out = decoded
                    nonce = int(topics[1], 16)
                    (nonce_used,) = self.eth_call(
                        vault_address,
                        "usedNonce(uint256)",
                        ("uint256",),
                        (nonce,),
                        ("bool",),
                    )
                    events.append(
                        {
                            "nonce": str(nonce),
                            "nonce_used_at_snapshot": nonce_used,
                            "policy_hash": topics[2],
                            "evidence_root": "0x" + root.hex(),
                            "token_in": token_in,
                            "token_out": token_out,
                            "amount_in_base_units": str(amount_in),
                            "amount_out_base_units": str(amount_out),
                        }
                    )
                except (DecodingError, ValueError, KeyError, TypeError):
                    raise FujiReadError("FUJI_BAD_RECEIPT") from None
        out["swap_events"] = events
        return out

    def snapshot(self, address, *, vault_address=None, tx_hash=None):
        holder = require_address(address)
        vault_address = require_address(vault_address) if vault_address else None
        self.pin_block()
        native = quantity(
            self.rpc("eth_getBalance", [holder, self.block_tag]),
            "FUJI_BAD_BALANCE",
        )
        assets = [
            {
                "symbol": "AVAX",
                "contract": None,
                "decimals": 18,
                "balance_base_units": str(native),
                "kind": "NATIVE_TEST_AVAX",
                "status": "VERIFIED",
            },
            self.token_balance(FUJI_USDC, holder, 6, "CIRCLE_FUJI_TEST_USDC"),
            self.token_balance(FUJI_WAVAX, holder, 18, "FUJI_TEST_WAVAX"),
        ]
        oracles = [chainlink(self, *feed) for feed in CHAINLINK_FEEDS]
        oracles.extend([self.oracle(), pyth(self)])
        out = {
            "network": "AVALANCHE_FUJI_TESTNET",
            "chain_id": FUJI_CHAIN_ID,
            "address": holder,
            "explorer_url": f"{EXPLORER}/address/{holder}",
            "block_number": self.block["number"],
            "block_hash": self.block["hash"],
            "block_timestamp": self.block["timestamp"],
            "observed_at": self.now,
            "rpc_url": FUJI_RPC,
            "assets": assets,
            "oracle": oracles[2],
            "oracles": oracles,
            "source": "FUJI_C_CHAIN_RPC",
            "execution_enabled": False,
            "used_for_sde_or_attestation": False,
            "warnings": [
                "Fuji test balances and external AVAX market references use different asset identities",
                "Vault assets are read from its usdc()/wavax() addresses",
                "USD portfolio valuation requires validated pricing for each vault asset",
            ],
        }
        out["vault"] = self.vault(vault_address) if vault_address else {"status": "NOT_CONFIGURED"}
        out["receipt"] = (
            self.receipt(tx_hash, vault_address) if tx_hash else {"status": "NOT_REQUESTED"}
        )
        out["market"] = self.market()
        self.verify_block()
        out["block_binding"] = "PINNED_HEIGHT_HASH_RECHECKED"
        out["snapshot_status"] = (
            "COMPLETE" if all(asset["status"] == "VERIFIED" for asset in assets) else "PARTIAL"
        )
        out["read_duration_ms"] = int((self.monotonic() - self.started) * 1000)
        out["observation_hash"] = "0x" + keccak(rfc8785.dumps(out)).hex()
        return out
