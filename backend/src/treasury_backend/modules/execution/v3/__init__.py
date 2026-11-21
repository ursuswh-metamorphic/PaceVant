"""Fixed operation execution port, composed into the existing FastAPI modular monolith."""

from web3 import Web3

from treasury_backend.modules.execution.storage import Store
from treasury_contracts.crypto import content_hash

from .builder import build_operation
from .context import V3Chain
from .relay import reconcile, relay
from .simulation import fork_simulate


class V3Execution:
    def __init__(self, settings, manifest, store=None):
        self.chain = V3Chain(settings, manifest)
        self.store = store or Store(settings.data_dir)
        self.manifest = manifest

    def context(self, session_id):
        return self.chain.context(session_id)

    def display_context(self, session_id):
        return self.chain.context(session_id, require_active=False)

    def exclusive(self):
        return self.store.lock

    def build(self, intent, context):
        callback = getattr(self, "on_activity", None)
        built = build_operation(self.chain, self.store, intent, context,
            on_check=(lambda check_id, status, **values: callback("BUILD", check_id, status, **values)) if callback else None)
        if callback:
            try:
                target = self.chain.adapter if intent.operation == "TOKEN_SWAP" else (
                    self.chain.usdc if intent.token_in == self.manifest.usdc else self.chain.wavax)
                method, arguments = target.decode_function_input(built["call"]["data"])
                values = {k: str(v) if isinstance(v, int) and not isinstance(v, bool) else v for k,v in arguments.items()}
                if method.fn_name == "transfer":
                    ordered = [arguments[field["name"]] for field in method.abi["inputs"]]
                    values = {"recipient": ordered[0], "amount": str(ordered[1])}
                decoded = {"method": method.fn_name, "arguments": values,
                           "target": built["call"]["target"], "value": built["call"]["value"]}
            except Exception:
                decoded = {"function_selector": built["call"]["data"][:10], "reason_code": "CALL_DECODE_UNAVAILABLE"}
            callback("BUILD", "CALL_DECODED", "PASS" if "method" in decoded else "UNKNOWN", observed=decoded)
        return built

    def simulate(self, build, context):
        evidence = fork_simulate(self.chain, build, context)
        self.store.put("v3-effects", build["build_id"], evidence)
        return evidence

    def preflight(self, build, context, operation, phi, signature):
        evidence = fork_simulate(self.chain, build, context, operation=operation, phi=phi, signature=signature)
        self.store.put("v3-preflight", build["build_id"], evidence)
        return evidence

    def revalidate(self, intent, built, context):
        current = self.context(intent.session_id)
        # Strict state freshness: a new candidate is required after any policy/budget/balance change.
        fields = ("policy_hash", "policy_version", "balances", "authority", "risk_remaining", "global_risk_remaining",
                  "spend_remaining", "daily_spend_remaining", "manifest_hash", "price_intervals", "share_rate")
        if any(current[k] != context[k] for k in fields):
            raise ValueError("STALE_REQUIRES_REEVALUATION")
        if context.get("mvp") and any(current[k]!=context[k] for k in (
            "swap_spend_remaining","payment_spend_remaining_usdc","daily_swap_remaining",
            "daily_payment_remaining_usdc","recipient_allowlist","gas_spent_or_reserved_wei")):
            raise ValueError("STALE_REQUIRES_REEVALUATION")
        if (current["timestamp"] > intent.deadline or Web3.to_hex(self.chain.w3.eth.get_block(context["block_number"]).hash)
                != context["block_hash"]):
            raise ValueError("STALE_REQUIRES_REEVALUATION")
        if content_hash(context) != built["context_hash"]:
            raise ValueError("HASH_MISMATCH")
        return current

    def execute(self, build, operation, phi, signature):
        return relay(self, build, operation, phi, signature)

    def reconcile(self, tx_hash):
        return reconcile(self, tx_hash)

    def submission_hash(self, build_id):
        with self.store.db() as db:
            row = db.execute("SELECT tx_hash FROM submissions WHERE build_id=?", (build_id,)).fetchone()
        return row[0] if row else None
