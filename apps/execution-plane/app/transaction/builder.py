import time
from web3 import Web3
from ..crypto import content_hash, keccak
from ..errors import PlaneError
from ..models import BuiltTransaction, TransactionProposal


class Builder:
    def __init__(self, chain, store):
        self.chain, self.store = chain, store

    def build(self, p: TransactionProposal):
        c = self.chain.context()
        for field, expected, code in [
            ("chain_id", c["chain_id"], "CHAIN_MISMATCH"),
            ("vault_address", c["vault_address"], "BAD_RECIPIENT"),
            ("router", c["router"], "ROUTER_NOT_ALLOWED"),
            ("token_in", c["token_in"], "TOKEN_NOT_ALLOWED"),
            ("token_out", c["token_out"], "TOKEN_NOT_ALLOWED"),
            ("recipient", c["vault_address"], "BAD_RECIPIENT"),
        ]:
            value = getattr(p, field)
            if str(value).lower() != str(expected).lower():
                raise PlaneError(code, f"Unsupported {field}")
        if (
            not c["policy_active"]
            or c["paused"]
            or c["policy_expires_at"] < c["timestamp"]
        ):
            raise PlaneError("POLICY_REVOKED", "Policy unavailable", 409)
        amount = int(p.amount_in_base_units)
        if amount <= 0 or amount > int(c["max_per_swap_base_units"]):
            raise PlaneError("TRADE_SIZE_LIMIT", "Trade exceeds mandate")
        if p.slippage_bps > c["max_slippage_bps"]:
            raise PlaneError("BAD_PRICE_OR_SLIPPAGE", "Slippage exceeds mandate")
        # Validate against both wall-clock and chain timestamp to fail closed if node is stale.
        now = max(int(time.time()), c["timestamp"])
        if (
            not now
            < p.deadline
            <= c["timestamp"] + min(self.chain.settings.max_ttl, c["max_approval_ttl"])
        ):
            raise PlaneError(
                "EXPIRED_APPROVAL",
                "Deadline must be within the 30-second demo TTL",
                409,
            )
        if p.deadline > c["policy_expires_at"]:
            raise PlaneError("POLICY_REVOKED", "Mandate expires before approval", 409)
        n = c["block_number"]
        v = self.chain.vault.functions
        if not v.allowedRouters(c["router"]).call(block_identifier=n):
            raise PlaneError("ROUTER_NOT_ALLOWED", "Router revoked")
        if not all(
            v.allowedTokens(c[k]).call(block_identifier=n)
            for k in ("token_in", "token_out")
        ):
            raise PlaneError("TOKEN_NOT_ALLOWED", "Token revoked")
        snapshot = self.chain.snapshot(c)
        if int(snapshot["usdc_base_units"]) < amount:
            raise PlaneError("INSUFFICIENT_BALANCE", "Insufficient vault USDC")
        if int(snapshot["daily_spent_usdc_base_units"]) + amount > int(
            c["max_spend_per_day_base_units"]
        ):
            raise PlaneError("DAILY_SPEND_LIMIT", "Daily budget exceeded")
        quote = self.chain.router.functions.quote(
            c["token_in"], c["token_out"], amount
        ).call(block_identifier=n)
        min_out = quote * (10000 - p.slippage_bps) // 10000
        if min_out <= 0:
            raise PlaneError("BAD_PRICE_OR_SLIPPAGE", "Zero minOut")
        data = self.chain.router.encode_abi(
            "exactInput",
            args=[c["token_in"], c["token_out"], amount, min_out, c["vault_address"]],
        )
        quote_artifact = self.store.artifact(
            {
                "context": c,
                "quote_out_base_units": str(quote),
                "slippage_bps": p.slippage_bps,
                "snapshot": snapshot,
                "bytecode_hashes": self.chain.deployment["bytecode_hashes"],
            }
        )
        nonce = self.store.nonce(f"{c['chain_id']}:{c['vault_address'].lower()}")
        while v.usedNonce(int(nonce)).call():
            nonce = self.store.nonce(f"{c['chain_id']}:{c['vault_address'].lower()}")
        fields = dict(
            intent_id=p.intent_id,
            chain_id=c["chain_id"],
            vault_address=c["vault_address"],
            router=c["router"],
            token_in=c["token_in"],
            token_out=c["token_out"],
            amount_in_base_units=str(amount),
            min_amount_out_base_units=str(min_out),
            router_calldata=data,
            calldata_hash=keccak(Web3.to_bytes(hexstr=data)),
            policy_hash=c["policy_hash"],
            nonce=nonce,
            deadline=p.deadline,
            quote_ref=quote_artifact["ref"],
            adapter_version="mock-swap-v1",
        )
        built = BuiltTransaction(build_id="build_" + content_hash(fields)[2:], **fields)
        self.store.put("build", built.build_id, built.model_dump())
        self.store.put(
            "build-context",
            built.build_id,
            {
                "context": c,
                "snapshot": snapshot,
                "output_per_usdc": str(
                    self.chain.router.functions.outputPerUsdc().call(block_identifier=n)
                ),
                "proposal": p.model_dump(),
            },
        )
        return built.model_dump()
