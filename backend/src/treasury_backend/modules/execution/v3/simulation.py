"""Real EVM effects on a disposable pinned fork; simulation sentinels never authorize relay."""

from fractions import Fraction

from eth_account import Account
from web3 import Web3

from treasury_backend.modules.execution.chain import contract
from treasury_backend.modules.execution.simulation.runner import fork_node, override_attestor, rpc
from treasury_contracts.crypto import content_hash
from treasury_contracts.proof import ceil_nonnegative
from treasury_contracts.v3 import ZERO, Constraints, Operation, operation_message


def tentative_constraints(build, context):
    intent = build["intent"]
    registry = [context["usdc"], context["wavax"], context["shares"], ZERO]
    i, j = registry.index(intent["token_in"]), registry.index(intent["token_out"])
    deltas = [-int(intent["amount"]) if k == i else int(build["min_output"]) if k == j and i != j else 0 for k in range(4)]
    return Constraints(before_balances=tuple(context["balances"]), min_deltas=tuple(str(v) for v in deltas),
                       receipt_credit=build["min_output"] if intent["operation"] == "TOKEN_PAYMENT" else "0",
                       max_wavax_balance=str(2**255 - 1))


def fork_simulate(chain, build, context, *, operation=None, phi=None, signature=None):
    final = operation is not None
    with fork_node(chain.settings, context["block_number"], chain.manifest.chain_id) as w3:
        vault = contract(w3, "PolicyVaultV3", chain.manifest.treasury)
        before = vault.functions.balances().call()
        if [str(v) for v in before] != context["balances"]:
            raise ValueError("FORK_STATE_MISMATCH")
        sender = Web3.to_checksum_address(chain.manifest.relayer)
        rpc(w3, "anvil_impersonateAccount", [sender])
        rpc(w3, "anvil_setBalance", [sender, hex(10**20)])
        overrides = []
        if not final:
            signer = Account.create()
            overrides.append(override_attestor(w3, vault.address, signer.address))
            phi = tentative_constraints(build, context)
            registry = [context["usdc"], context["wavax"], context["shares"], ZERO]
            i = registry.index(build["intent"]["token_in"])
            units = [10**6, 10**18, int(context["share_unit"]), 10**18]
            spend = ceil_nonnegative(Fraction(int(build["intent"]["amount"]) * int(context["price_intervals"][i][1]), units[i]))
            if i == 0:
                spend = max(spend, int(build["intent"]["amount"]) * 100)
            operation = Operation.model_validate(build["operation"] | {
                "evidenceRoot": content_hash({"SIMULATION_ONLY": build["build_id"]}),
                "proofContextHash": content_hash({"SIMULATION_SENTINEL_NOT_A_PROOF": True}),
                "constraintsHash": phi.hash, "spendDebitUsdE8": str(spend)})
            signature = Web3.to_hex(Account.sign_message(operation_message(chain.manifest.chain_id, vault.address, operation), signer.key).signature)
        token = contract(w3, "MockUSDC", operation.tokenIn) if operation.tokenIn != ZERO else None
        recipient = Web3.to_checksum_address(operation.recipient)
        receipt_before = (w3.eth.get_balance(recipient) if token is None else token.functions.balanceOf(recipient).call()) if operation.kind == 2 else 0
        tx = vault.functions.executeOperation(operation.abi_tuple, phi.abi_tuple, signature).transact({"from": sender, "gas": 4_000_000})
        receipt = w3.eth.wait_for_transaction_receipt(tx, timeout=30)
        if receipt.status != 1:
            # Re-run eth_call to preserve a bounded revert reason in the caller's error evidence.
            try:
                vault.functions.executeOperation(operation.abi_tuple, phi.abi_tuple, signature).call({"from": sender})
            except Exception as exc:
                raw=getattr(exc,"data",None)
                selector=raw[:10] if isinstance(raw,str) and raw.startswith("0x") else ""
                errors={"SessionUnavailable()":"SESSION_UNAVAILABLE","ScopeViolation()":"SESSION_SPENDING_OR_SCOPE_LIMIT",
                        "SessionRiskLimit()":"SESSION_RISK_LIMIT","GlobalRiskLimit()":"GLOBAL_RISK_LIMIT",
                        "DailySpendLimit()":"DAILY_SPEND_LIMIT","ReceiptNotMet()":"PAYEE_RECEIPT_SHORTFALL",
                        "PostConditionFailed()":"POSTCONDITION_VIOLATION","StateDrift()":"STATE_DRIFT",
                        "PolicyRevoked()":"POLICY_REVOKED","ExpiredApproval()":"EXPIRED_APPROVAL",
                        "UnsupportedOperation()":"MVP_UNSUPPORTED_OPERATION","TradeSizeLimit()":"TRADE_SIZE_LIMIT"}
                reason=next((name for signature,name in errors.items() if Web3.to_hex(Web3.keccak(text=signature)[:4])==selector),"EVM_SIMULATION_REVERTED")
                raise ValueError(reason) from None
            raise ValueError("EVM_SIMULATION_REVERTED")
        after = vault.functions.balances().call()
        received = ((w3.eth.get_balance(recipient) if token is None else token.functions.balanceOf(recipient).call()) - receipt_before) if operation.kind == 2 else 0
        usdc, wavax = [contract(w3, name, address) for name, address in (
            ("MockUSDC", chain.manifest.usdc), ("MockWAVAX", chain.manifest.wavax))]
        allowance_pairs = [(usdc, chain.manifest.adapter), (wavax, chain.manifest.adapter)]
        if not getattr(chain,"is_mvp",False):
            shares = contract(w3,"DemoERC4626",chain.manifest.shares)
            allowance_pairs.extend(((usdc,chain.manifest.shares),(shares,chain.manifest.adapter)))
        allowances = [t.functions.allowance(vault.address, Web3.to_checksum_address(spender)).call()
                      for t, spender in allowance_pairs]
        return {"source": "LOCAL_FORK_EVM", "environment": chain.manifest.environment,
                "execution_status": "SUCCESS", "build_hash": content_hash(build),
                "source_block": context["block_number"], "source_block_hash": context["block_hash"],
                "before": [str(v) for v in before], "after": [str(v) for v in after],
                "deltas": [str(b - a) for a, b in zip(before, after, strict=True)],
                "received": str(received), "allowances": [str(v) for v in allowances],
                "gas_used": int(receipt.gasUsed), "simulation_overrides": overrides,
                "exact_signed_preflight": final, "fork_tx_hash": Web3.to_hex(tx),
                "public_chain_receipt": False}
