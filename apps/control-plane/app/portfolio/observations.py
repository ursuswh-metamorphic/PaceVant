"""Fresh or historical pinned observations. These objects never grant permission."""

import time
from urllib.parse import urlsplit

import rfc8785
from eth_abi import decode, encode
from eth_utils import keccak
from web3 import Web3

from app.domain import AssetObservation, ObservedPortfolioSnapshot, PriceObservation
from app.errors import ControlError
from app.fuji_data import FujiReader
from app.fuji_oracles import CHAINLINK_FEEDS, chainlink, pyth
from app.fuji_rpc import FujiReadError
from treasury_contracts.onchain import vault_abi
from treasury_contracts.readonly import ReadError, readonly_web3

LFJ_USDC = "0xb6076c93701d6a07266c31066b298aec6dd65c2d"
WAVAX = "0xd00ae08403b9bbb9124bb305c09058e32c39a48c"


def content_hash(fields):
    return "0x" + keccak(rfc8785.dumps(fields)).hex()


def observed(fields):
    draft = ObservedPortfolioSnapshot(
        snapshot_id="observed_pending", content_hash="0x" + "00" * 32, **fields
    )
    digest = content_hash(draft.model_dump(exclude={"snapshot_id", "content_hash"}))
    return draft.model_copy(
        update={"snapshot_id": "observed_" + digest[2:], "content_hash": digest}
    )


def verify_snapshot_hash(snapshot):
    value = snapshot.model_dump()
    digest = value.pop("content_hash")
    value.pop("snapshot_id")
    return digest == content_hash(value)


class OracleBridge:
    def __init__(self, w3, block, now):
        self.w3, self.block, self.now = w3, block, now

    def code(self, address):
        try:
            raw = self.w3.eth.get_code(Web3.to_checksum_address(address), self.block["number"])
            if not raw:
                raise FujiReadError("FUJI_CONTRACT_NOT_DEPLOYED")
            return "0x" + keccak(raw).hex()
        except Exception:
            raise FujiReadError("CONTRACT_CODE_UNAVAILABLE") from None

    def eth_call(self, address, signature, types=(), values=(), returns=("uint256",)):
        try:
            data = keccak(text=signature)[:4] + encode(types, values)
            raw = self.w3.eth.call(
                {"to": Web3.to_checksum_address(address), "data": data},
                block_identifier=self.block["number"],
            )
            result = decode(returns, raw)
            if encode(returns, result) != raw:
                raise ValueError("noncanonical ABI")
            return result
        except Exception:
            raise FujiReadError("ORACLE_READ_UNAVAILABLE") from None


class PortfolioReader:
    def __init__(self, mode, rpc_url, *, clock=time.time, client=None):
        if mode not in {"LOCAL", "FUJI"}:
            raise ControlError("INVALID_OBSERVATION_MODE", 400)
        self.mode, self.rpc_url, self.clock, self.client = mode, rpc_url, clock, client

    def collect(
        self,
        vault_address,
        *,
        mandate=None,
        block_number=None,
        history_version=0,
        independent_reader=None,
        include_oracles=True,
    ):
        chain_id = 31337 if self.mode == "LOCAL" else 43113
        w3 = readonly_web3(self.rpc_url, chain_id, client=self.client, seconds=35)
        try:
            return self._collect(
                w3,
                chain_id,
                vault_address,
                mandate,
                block_number,
                history_version,
                independent_reader,
                include_oracles,
            )
        except ControlError:
            raise
        except ReadError as error:
            raise ControlError(error.code, 503, retryable=True) from None
        except Exception:
            raise ControlError("PORTFOLIO_SOURCE_UNAVAILABLE", 503, retryable=True) from None
        finally:
            w3.provider.close()

    def _collect(
        self,
        w3,
        chain_id,
        vault_address,
        mandate,
        block_number,
        history_version,
        independent_reader,
        include_oracles,
    ):
        now = int(self.clock())
        vault_address = Web3.to_checksum_address(vault_address)
        header = w3.eth.get_block(block_number if block_number is not None else "latest")
        n = header.number
        if (
            len(header.hash) != 32
            or header.timestamp > now + 5
            or (block_number is not None and n != block_number)
        ):
            raise ControlError("BLOCK_HASH_MISMATCH")
        issues = []
        if block_number is None and now - header.timestamp > 60:
            issues.append("STALE_SNAPSHOT")
        state = {}
        policy_hash = policy_version = None
        bridge = OracleBridge(
            w3, {"number": n, "timestamp": header.timestamp, "hash": Web3.to_hex(header.hash)}, now
        )
        tokens = [
            mandate.token_in if mandate else LFJ_USDC,
            mandate.token_out if mandate else WAVAX,
        ]
        try:
            vault_code = bridge.code(vault_address)
            v = w3.eth.contract(address=vault_address, abi=vault_abi()).functions
            tokens = [v.usdc().call(block_identifier=n), v.wavax().call(block_identifier=n)]
            policy_hash = Web3.to_hex(v.activePolicyHash().call(block_identifier=n))
            policy_version = v.policyVersion().call(block_identifier=n)
            state = {
                "owner": v.owner().call(block_identifier=n).lower(),
                "attestor": v.attestor().call(block_identifier=n).lower(),
                "active": v.policyActive().call(block_identifier=n),
                "paused": v.paused().call(block_identifier=n),
                "bytecode_hash": vault_code,
            }
        except Exception:
            issues.append("VAULT_POLICY_UNAVAILABLE")
        if mandate:
            if (chain_id, vault_address.lower()) != (mandate.chain_id, mandate.vault_address):
                issues.append("MANDATE_SCOPE_MISMATCH")
            if [a.lower() for a in tokens] != [mandate.token_in, mandate.token_out]:
                issues.append("TOKEN_IDENTITY_MISMATCH")
            if policy_hash != mandate.policy_hash:
                issues.append("POLICY_HASH_MISMATCH")
            if state.get("owner") != mandate.owner:
                issues.append("MANDATE_OWNER_MISMATCH")
        assets = []
        try:
            native = str(w3.eth.get_balance(vault_address, n))
            native_status = "VERIFIED"
        except Exception:
            native, native_status = None, "UNAVAILABLE"
        assets.append(
            AssetObservation(
                asset_id=f"{chain_id}:native",
                contract=None,
                symbol="AVAX",
                decimals=18,
                balance_base_units=native,
                verification_status=native_status,
            )
        )
        for address, expected, symbol in zip(tokens, [6, 18], ["USDC", "WAVAX"], strict=True):
            data = {
                "asset_id": f"{chain_id}:erc20:{address.lower()}",
                "contract": address.lower(),
                "symbol": symbol,
                "decimals": None,
                "balance_base_units": None,
                "verification_status": "UNAVAILABLE",
            }
            try:
                data["bytecode_hash"] = bridge.code(address)
                (decimals,) = bridge.eth_call(address, "decimals()", returns=("uint8",))
                data["decimals"] = decimals
                (balance,) = bridge.eth_call(
                    address, "balanceOf(address)", ("address",), (vault_address,)
                )
                data["balance_base_units"] = str(balance)
                data["verification_status"] = "VERIFIED" if decimals == expected else "UNVERIFIED"
                if decimals != expected:
                    data["reason_codes"] = ["TOKEN_DECIMALS_MISMATCH"]
            except Exception:
                data["reason_codes"] = ["TOKEN_READ_UNAVAILABLE"]
            assets.append(AssetObservation(**data))
        if any(asset.verification_status != "VERIFIED" for asset in assets):
            issues.append("ASSET_OBSERVATION_INCOMPLETE")
        check = "NOT_AVAILABLE"
        if independent_reader:
            try:
                remote = independent_reader(n)
            except Exception:
                remote = None
                issues.append("INDEPENDENT_READER_UNAVAILABLE")
            if remote is None:
                remote = {}
            mismatch = (
                remote.get("chain_id") != chain_id
                or remote.get("vault_address", "").lower() != vault_address.lower()
                or remote.get("block_number") != n
                or remote.get("block_hash") != Web3.to_hex(header.hash)
                or remote.get("timestamp") != header.timestamp
                or remote.get("policy_hash") != policy_hash
                or remote.get("usdc_base_units") != assets[1].balance_base_units
                or remote.get("wavax_base_units") != assets[2].balance_base_units
            )
            check = "MISMATCH" if mismatch else "MATCHED"
            if mismatch:
                issues.append("INDEPENDENT_BALANCE_MISMATCH")
        prices = []
        if include_oracles and self.mode == "FUJI":
            sources = [chainlink(bridge, *feed) for feed in CHAINLINK_FEEDS]
            sources.extend([FujiReader.oracle(bridge), pyth(bridge)])
            for item in sources:
                reason = [item["reason_code"]] if item.get("reason_code") else []
                if item["pair"] == "USDC/USD" and tokens[0].lower() == LFJ_USDC:
                    reason.append("ORACLE_TOKEN_IDENTITY_MISMATCH")
                if not item.get("updated_at") or now - item["updated_at"] > 60:
                    reason.append("PRICE_NOT_FRESH_FOR_RISK")
                prices.append(
                    PriceObservation(
                        provider=item["provider"],
                        feed_contract=item["contract"],
                        represented_pair=item["pair"],
                        price_usd_e8=item.get("price_usd_e8"),
                        decimals=item.get("decimals"),
                        updated_at=item.get("updated_at"),
                        round_id=item.get("round_id"),
                        status=item["status"],
                        display_eligible=bool(item.get("price_usd_e8")),
                        source_ref=item.get("feed_id")
                        or item.get("pair_id")
                        or item.get("source_url"),
                        reason_codes=reason,
                    )
                )
        if Web3.to_hex(w3.eth.get_block(n).hash) != Web3.to_hex(header.hash):
            raise ControlError("BLOCK_HASH_MISMATCH")
        parsed = urlsplit(self.rpc_url)
        source_id = (
            parsed.scheme + "://" + parsed.netloc + "#path-" + keccak(text=parsed.path).hex()[:16]
        )
        return observed(
            dict(
                mode=self.mode,
                chain_id=chain_id,
                vault_address=vault_address.lower(),
                block_number=n,
                block_hash=Web3.to_hex(header.hash),
                block_timestamp=header.timestamp,
                observed_at=now,
                source_rpc_id=source_id,
                policy_hash=policy_hash,
                policy_version=policy_version,
                policy_state=state,
                assets=[a.model_dump() for a in assets],
                price_observations=[p.model_dump() for p in prices],
                history_version=history_version,
                verification_status="VERIFIED" if not issues else "INCOMPLETE",
                reason_codes=list(dict.fromkeys(issues)),
                source_refs=[Web3.to_hex(header.hash)],
                authorization_eligible=False,
                independent_balance_check=check,
            )
        )
