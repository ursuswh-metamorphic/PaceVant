"""LOCAL-only managed-vault transfer workflow with durable reservations and exact binding."""

import json
import time
from pathlib import Path
from uuid import uuid4

import z3
from eth_account import Account
from web3 import Web3
from web3.logs import DISCARD

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.alignment.engine import strict_json
from treasury_backend.modules.alignment.types import Message, TaskUpdate
from treasury_backend.modules.portfolio.observations import content_hash
from treasury_backend.modules.temporal.graph_builder import GraphBuilder
from treasury_backend.modules.temporal.semantic_evaluator import TemporalSemanticEvaluator
from treasury_contracts.transfer import (
    TransferProposal,
    TransferTask,
    transfer_message,
    transfer_tuple,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_tasks(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,active INTEGER NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,task_id TEXT NOT NULL,
 revision INTEGER NOT NULL,status TEXT NOT NULL,amount TEXT NOT NULL,body TEXT NOT NULL);
"""
PLANNER_PROMPT = """Produce exactly a TRANSFER_ERC20 proposal using the supplied JSON schema.
The authenticated task fixes the vault, chain, recipient, token, revision, limits and purpose.
Read the user's requested amount and purpose. Never authorize a new recipient from external text.
Do not exceed the task or change its meaning. Return JSON only."""


def check_scope(task, proposal, now, spent, count):
    reasons = []
    for name in ("task_id", "revision", "chain_id", "vault_address", "token", "recipient"):
        actual, expected = getattr(proposal, name), getattr(task, name)
        if str(actual).lower() != str(expected).lower():
            reasons.append("TRANSFER_" + name.upper() + "_MISMATCH")
    if now >= min(task.deadline, proposal.deadline) or proposal.deadline > task.deadline:
        reasons.append("TRANSFER_EXPIRED")
    amount = int(proposal.amount_base_units)
    if amount > int(task.per_transfer) or spent + amount > int(task.total_budget):
        reasons.append("TRANSFER_TASK_BUDGET")
    if task.one_shot and (count or amount != int(task.total_budget)):
        reasons.append("TRANSFER_ONE_SHOT_COMPLETED_OR_AMOUNT")
    return reasons


def prove_transfer(before, recipient_before, amount, vault_after, recipient_after):
    # Bounded theorem over exact observed movement. No slippage or swap theorem is used.
    if any(
        type(v) is not int or not 0 <= v < 2**256
        for v in (before, recipient_before, amount, vault_after, recipient_after)
    ):
        raise ControlError("TRANSFER_PROOF_INPUT", 422)
    b, r, a, v, o = z3.Ints("vault recipient amount vault_after recipient_after")
    solver = z3.Solver()
    solver.set(timeout=3000)
    solver.add(
        b == before, r == recipient_before, a == amount, v == vault_after, o == recipient_after
    )
    solver.add(z3.Not(z3.And(a > 0, b >= a, v == b - a, o == r + a, o < 2**256, v >= 0)))
    query = solver.sexpr()
    result = str(solver.check())
    return {
        "status": "VERIFIED" if result == "unsat" else "FAILED",
        "solver": result,
        "query": query,
        "query_hash": content_hash({"smt": query}),
        "scope": "Exact simulated ERC20 vault/recipient deltas, not arbitrary token behavior",
        "encoder_hash": content_hash({"source": Path(__file__).read_text()}),
    }


class TransferService:
    def __init__(self, control, execution):
        self.control, self.runtime = control, execution.runtime
        self.execution = execution
        self.store = control.store
        with self.store.connection() as db:
            db.executescript(SCHEMA)

    def local(self):
        if (
            self.control.settings.mode != "LOCAL"
            or self.runtime is None
            or self.runtime.chain.chain_id != 31337
            or not self.runtime.chain.w3.client_version.lower().startswith("anvil")
        ):
            raise ControlError("TRANSFER_LOCAL_ONLY", 409)
        if not self.control.shield.active:
            raise ControlError("TASK_SHIELD_REQUIRED", 409)
        return self.runtime.chain

    def authorize(self, task):
        chain = self.local()
        if (
            task.chain_id != chain.chain_id
            or task.vault_address.lower() != chain.vault.address.lower()
        ):
            raise ControlError("TRANSFER_SOURCE_MISMATCH", 422)
        self.rule(chain, task.token, task.recipient, int(time.time()))
        with self.store.connection(write=True) as db:
            old = db.execute(
                "SELECT revision,body FROM payment_tasks WHERE id=?", (task.task_id,)
            ).fetchone()
            if old:
                prior = TransferTask.model_validate_json(old["body"])
                if any(
                    str(getattr(prior, k)).lower() != str(getattr(task, k)).lower()
                    for k in ("chain_id", "vault_address", "token", "recipient")
                ):
                    raise ControlError("TRANSFER_TASK_SCOPE_IMMUTABLE", 409)
            expected = old["revision"] + 1 if old else 1
            if task.revision != expected:
                raise ControlError("TRANSFER_REVISION_CONFLICT", 409)
            if (
                old
                and db.execute(
                    "SELECT 1 FROM payments WHERE task_id=? AND status IN ('EVALUATING','APPROVED','SUBMITTING','PENDING','RECEIPT_MISMATCH')",
                    (task.task_id,),
                ).fetchone()
            ):
                raise ControlError("TRANSFER_PENDING_RESERVATION", 409)
            db.execute(
                "INSERT INTO payment_tasks VALUES (?,?,1,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,active=1,body=excluded.body",
                (task.task_id, task.revision, task.model_dump_json()),
            )
        return task

    def cancel(self, task_id):
        self.local()
        with self.store.connection(write=True) as db:
            if db.execute(
                "SELECT 1 FROM payments WHERE task_id=? AND status IN ('SUBMITTING','PENDING','RECEIPT_MISMATCH')",
                (task_id,),
            ).fetchone():
                raise ControlError("TRANSFER_PENDING_RESERVATION", 409)
            db.execute("UPDATE payment_tasks SET active=0 WHERE id=?", (task_id,))
        return {"task_id": task_id, "active": False}

    def task(self, db, task_id, revision):
        row = db.execute("SELECT * FROM payment_tasks WHERE id=?", (task_id,)).fetchone()
        if not row or not row["active"] or row["revision"] != revision:
            raise ControlError("TRANSFER_TASK_INACTIVE_OR_STALE", 409)
        return TransferTask.model_validate_json(row["body"])

    def rule(self, chain, token, recipient, now):
        if token.lower() not in {chain.usdc.address.lower(), chain.wavax.address.lower()}:
            raise ControlError("TRANSFER_TOKEN_NOT_ALLOWED", 422)
        rule = chain.vault.functions.transferRecipients(
            Web3.to_checksum_address(token), Web3.to_checksum_address(recipient)
        ).call()
        if not rule[5] or rule[2] <= now or not rule[3]:
            raise ControlError("TRANSFER_RECIPIENT_NOT_AUTHORIZED", 422)
        erc = self.execution.token_contract(chain.w3, "MockUSDC", Web3.to_checksum_address(token))
        if erc.functions.decimals().call() != rule[4]:
            raise ControlError("TRANSFER_DECIMALS_MISMATCH", 422)
        return rule, erc

    def save(self, id_, status, body):
        with self.store.connection(write=True) as db:
            db.execute(
                "UPDATE payments SET status=?,body=? WHERE id=?", (status, json.dumps(body), id_)
            )
        return {"request_id": id_, "status": status, **body}

    def read(self, id_):
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM payments WHERE id=?", (id_,)).fetchone()
        if not row:
            raise ControlError("TRANSFER_NOT_FOUND", 404)
        return {"request_id": id_, "status": row["status"], **json.loads(row["body"])}

    def run(self, request):
        chain = self.local()
        request_hash = content_hash(request.model_dump(mode="json"))
        with self.store.connection() as db:
            monitored = [
                r["id"]
                for r in db.execute(
                    "SELECT id FROM payments WHERE task_id=? AND status IN ('CONFIRMED','SUBMITTING','PENDING','RECEIPT_MISMATCH')",
                    (request.task_id,),
                )
            ]
        for payment in monitored:
            self.reconcile(payment)
        with self.store.connection(write=True) as db:
            old = db.execute("SELECT * FROM payments WHERE id=?", (request.request_id,)).fetchone()
            if old:
                if old["request_hash"] != request_hash:
                    raise ControlError("TRANSFER_IDEMPOTENCY_CONFLICT", 409)
                return {"request_id": old["id"], "status": old["status"], **json.loads(old["body"])}
            task = self.task(db, request.task_id, request.revision)
            # Serialize outflow by task while model inference occurs outside write transactions.
            if db.execute(
                "SELECT 1 FROM payments WHERE task_id=? AND status IN ('EVALUATING','APPROVED','SUBMITTING','PENDING','RECEIPT_MISMATCH')",
                (task.task_id,),
            ).fetchone():
                raise ControlError("TRANSFER_PENDING_RESERVATION", 409)
            db.execute(
                "INSERT INTO payments VALUES (?,?,?,?,?,?,?)",
                (
                    request.request_id,
                    request_hash,
                    task.task_id,
                    task.revision,
                    "EVALUATING",
                    "0",
                    "{}",
                ),
            )
        body = {"task": task.model_dump(mode="json"), "source": "LOCAL_ANVIL", "broadcast": False}
        try:
            return self.evaluate(request, task, chain, body)
        except ControlError as error:
            return self.save(
                request.request_id, "ESCALATED", {**body, "reason_codes": [error.code]}
            )
        except Exception:
            # Once signed bytes may have reached the node, retain the reservation.
            current = self.read(request.request_id)
            if current["status"] in {"SUBMITTING", "PENDING", "RECEIPT_MISMATCH"}:
                return current
            return self.save(
                request.request_id,
                "ESCALATED",
                {**body, "reason_codes": ["TRANSFER_EVALUATION_UNAVAILABLE"]},
            )

    def evaluate(self, request, task, chain, body):
        now = int(time.time())
        deadline = min(task.deadline, now + min(120, chain.context()["max_approval_ttl"]))
        response = self.control.shield.provider.complete(
            [
                {"role": "system", "content": PLANNER_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": task.model_dump(mode="json"),
                            "goal": request.goal,
                            "authorized_amount_base_units": request.amount_base_units
                            or (task.total_budget if task.one_shot else None),
                            "intent_id": "payment_" + uuid4().hex,
                            "deadline": deadline,
                            "schema": TransferProposal.model_json_schema(),
                        }
                    ),
                },
            ]
        )
        proposal = TransferProposal.model_validate(strict_json(response.content))
        body["proposal"] = proposal.model_dump(mode="json")
        with self.store.connection() as db:
            history = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM payments WHERE task_id=? AND id!=?",
                    (task.task_id, request.request_id),
                )
            ]
        # All confirmed task revisions consume the same authorization budget.
        spent = sum(int(r["amount"]) for r in history if r["status"] == "CONFIRMED")
        count = sum(r["status"] == "CONFIRMED" for r in history)
        reasons = check_scope(task, proposal, now, spent, count)
        requested_amount = request.amount_base_units
        if requested_amount is None and task.one_shot:
            requested_amount = task.total_budget
        if requested_amount is None or proposal.amount_base_units != requested_amount:
            reasons.append("TRANSFER_REQUEST_AMOUNT_MISMATCH")
        rule = token = None
        try:
            rule, token = self.rule(chain, proposal.token, proposal.recipient, now)
            before = token.functions.balanceOf(chain.vault.address).call()
            if (
                before < int(proposal.amount_base_units)
                or int(proposal.amount_base_units) > rule[0]
            ):
                reasons.append("TRANSFER_BALANCE_OR_POLICY_CAP")
        except ControlError as error:
            reasons.append(error.code)
        body["temporal"] = {
            "spent": str(spent),
            "remaining": str(max(0, int(task.total_budget) - spent)),
            "verdict": "REJECT" if reasons else "PASS",
            "reason_codes": reasons,
        }
        session = "transfer_" + uuid4().hex
        shield = self.control.shield
        mandate = self.control.mandate()
        shield.state.create(session, mandate, now)
        tasks = shield.update_user(
            session,
            TaskUpdate(message_id="user_" + session, content=task.objective, expected_revision=0),
            authenticated=True,
        )["tasks"]
        report = shield.check(
            session,
            Message(
                message_id="candidate_" + session,
                role="ASSISTANT",
                content=json.dumps(proposal.model_dump(mode="json")),
                tool_name="transfer_erc20",
            ),
            tool={"tool_name": "transfer_erc20", "arguments": proposal.model_dump(mode="json")},
        )
        graph = GraphBuilder()
        scope = f"{task.task_id}:{task.revision}"
        graph.node(
            scope,
            "AUTHENTICATED_USER_INTENT",
            "AUTHENTICATED",
            [content_hash(task.model_dump(mode="json"))],
            {
                "authorization_source": "OPERATOR_API",
                "status": "AUTHENTICATED",
                "revision": task.revision,
                "terms": {
                    "objective": task.objective,
                    "total_budget": task.total_budget,
                    "recipient": task.recipient,
                    "token": task.token,
                },
            },
        )
        graph.node(
            proposal.intent_id,
            "AGENT_ACTION",
            "UNVERIFIED",
            [proposal.intent_id],
            {"proposal": proposal.model_dump(mode="json")},
        )
        graph.link(scope, proposal.intent_id, "DEPENDS_ON", [scope])
        for t in tasks:
            graph.node(
                t["instruction_id"],
                "AUTHENTICATED_USER_INTENT",
                "MODEL_JUDGMENT",
                [t["source_message_id"]],
                t,
            )
        for h in history:
            record = json.loads(h["body"])
            graph.node(
                "payment:" + h["id"],
                "TRANSACTION_OUTCOME",
                "VERIFIED_RECORD" if h["status"] == "CONFIRMED" else "UNVERIFIED",
                [content_hash(record)],
                {"state": h["status"], "record": record},
            )
        semantic = TemporalSemanticEvaluator(shield).before_decision(
            graph.finish(), proposal.intent_id, "ALIGNED", shield_blocked=report.status != "ALIGNED"
        )
        body.update(
            shield=report.model_dump(mode="json"),
            graph=graph.finish().model_dump(mode="json"),
            semantic=semantic.model_dump(mode="json"),
        )
        if report.status != "ALIGNED" or semantic.verdict != "ALIGNED" or reasons:
            verdict = (
                "REJECTED"
                if reasons or semantic.verdict == "MISALIGNED" or report.status == "MISALIGNED"
                else "ESCALATED"
            )
            body["sde"] = {"verdict": verdict, "reason_codes": reasons + semantic.reason_codes}
            return self.save(request.request_id, verdict, body)
        return self.approve_and_submit(request, task, proposal, chain, rule, token, body)

    def snapshot(self, chain, task, proposal):
        rule, token = self.rule(chain, proposal.token, proposal.recipient, int(time.time()))
        c = chain.context()
        return {
            "policy_hash": c["policy_hash"],
            "session": c["proof_session"],
            "transfer_version": chain.vault.functions.transferPolicyVersion().call(),
            "rule": list(rule),
            "balance": str(token.functions.balanceOf(chain.vault.address).call()),
            "recipient_balance": str(
                token.functions.balanceOf(Web3.to_checksum_address(proposal.recipient)).call()
            ),
        }

    def approve_and_submit(self, request, task, proposal, chain, rule, token, body):
        from secrets import randbits

        snapshot = self.snapshot(chain, task, proposal)
        amount = int(proposal.amount_base_units)
        risk = (amount * rule[3] + 10 ** rule[4] - 1) // 10 ** rule[4]
        session = snapshot["session"]
        approval = dict(
            intentHash=content_hash(proposal.model_dump(mode="json")),
            taskHash=content_hash(
                {
                    "id": task.task_id,
                    "revision": task.revision,
                    "terms": task.model_dump(mode="json"),
                }
            ),
            policyHash=snapshot["policy_hash"],
            evidenceRoot=content_hash({"SIMULATION_ONLY": request.request_id}),
            proofContextHash=content_hash({"SIMULATION_ONLY": proposal.model_dump(mode="json")}),
            sessionId=session["session_id"],
            transferPolicyVersion=snapshot["transfer_version"],
            taskBudget=int(task.total_budget),
            riskDebitUsdE8=risk,
            nonce=randbits(128),
            deadline=proposal.deadline,
            token=proposal.token,
            recipient=proposal.recipient,
            amount=amount,
        )
        # First simulation uses a separate ephemeral attestor on an isolated fork only.
        # The production attestor has not signed an approval at this stage.
        block = chain.w3.eth.block_number
        with self.execution.simulation_fork(chain.settings, block, 31337) as fork:
            simulator = Account.create()
            self.execution.simulation_attestor(fork, chain.vault.address, simulator.address)
            self.execution.simulation_rpc(
                fork, "anvil_setBalance", [simulator.address, hex(10**20)]
            )
            vault = self.execution.token_contract(fork, "PolicyVault", chain.vault.address)
            asset = self.execution.token_contract(fork, "MockUSDC", proposal.token)
            before = asset.functions.balanceOf(chain.vault.address).call()
            recipient_before = asset.functions.balanceOf(
                Web3.to_checksum_address(proposal.recipient)
            ).call()
            signed = Account.sign_message(
                transfer_message(31337, chain.vault.address, approval), simulator.key
            )
            call = vault.functions.executeApprovedTransferV2(
                transfer_tuple(approval), signed.signature
            )
            tx = call.build_transaction(
                {
                    "from": simulator.address,
                    "nonce": 0,
                    "gas": 1500000,
                    "gasPrice": fork.eth.gas_price,
                }
            )
            receipt = fork.eth.wait_for_transaction_receipt(
                fork.eth.send_raw_transaction(simulator.sign_transaction(tx).raw_transaction)
            )
            if receipt.status != 1:
                raise ControlError("TRANSFER_SIMULATION_REVERTED", 409)
            proof = prove_transfer(
                before,
                recipient_before,
                amount,
                asset.functions.balanceOf(chain.vault.address).call(),
                asset.functions.balanceOf(Web3.to_checksum_address(proposal.recipient)).call(),
            )
            if proof["status"] != "VERIFIED":
                raise ControlError("TRANSFER_PROOF_FAILED", 409)
            body["simulation"] = {
                "source": "ISOLATED_ANVIL_FORK",
                "block": block,
                "block_hash": Web3.to_hex(chain.w3.eth.get_block(block).hash),
                "vault_before": str(before),
                "recipient_before": str(recipient_before),
                "vault_after": str(before - amount),
                "recipient_after": str(recipient_before + amount),
                "gas_used": str(receipt.gasUsed),
                "attestor_override": "SIMULATION_ONLY",
                "vault_bytecode_hash": Web3.to_hex(
                    Web3.keccak(chain.w3.eth.get_code(chain.vault.address))
                ),
                "token_bytecode_hash": Web3.to_hex(
                    Web3.keccak(chain.w3.eth.get_code(proposal.token))
                ),
            }
        body["proof"] = proof
        body["risk"] = {
            "result": "PASS",
            "outflow_usd_e8": str(risk),
            "valuation_source": "OWNER_LOCAL_REFERENCE",
            "per_transfer": str(rule[0]),
            "daily": str(rule[1]),
        }
        approval["evidenceRoot"] = content_hash(
            {"simulation": body["simulation"], "risk": body["risk"], "graph": body["graph"]}
        )
        approval["proofContextHash"] = content_hash(
            {"proof": proof, "intent": approval["intentHash"], "snapshot": snapshot}
        )
        # Exact snapshot, bytecode, task revision and reservations are checked again before signing.
        if self.snapshot(chain, task, proposal) != snapshot or time.time() >= proposal.deadline:
            raise ControlError("TRANSFER_STALE_EVIDENCE", 409)
        from treasury_backend.modules.decision.transfer import decide_transfer

        body["sde"] = decide_transfer(proposal, body)
        if body["sde"]["verdict"] != "APPROVE":
            return self.save(request.request_id, "ESCALATED", body)
        with self.store.connection(write=True) as db:
            self.task(db, task.task_id, task.revision)
            row = db.execute(
                "SELECT status FROM payments WHERE id=?", (request.request_id,)
            ).fetchone()
            if row["status"] != "EVALUATING":
                raise ControlError("TRANSFER_RESERVATION_CHANGED", 409)
            db.execute(
                "UPDATE payments SET status='APPROVED',amount=?,body=? WHERE id=?",
                (str(amount), json.dumps(body), request.request_id),
            )
        # A signature is internal evidence. This API never returns approval signatures or raw transactions.
        key = self.control.settings.attestor_key
        signature = Account.sign_message(
            transfer_message(31337, chain.vault.address, approval), key
        ).signature
        fn = chain.vault.functions.executeApprovedTransferV2(transfer_tuple(approval), signature)
        account = Account.from_key(chain.settings.relayer_private_key.get_secret_value())
        gas = fn.estimate_gas({"from": account.address})
        if gas * chain.w3.eth.gas_price > 10**17:
            raise ControlError("TRANSFER_GAS_LIMIT", 409)
        if self.snapshot(chain, task, proposal) != snapshot:
            raise ControlError("TRANSFER_STALE_PRE_SUBMIT", 409)
        with self.store.connection(write=True) as db:
            self.task(db, task.task_id, task.revision)
        transaction = fn.build_transaction(
            {
                "from": account.address,
                "chainId": 31337,
                "nonce": self.runtime.store.transaction_nonce(
                    account.address, chain.w3.eth.get_transaction_count(account.address, "pending")
                ),
                "gas": gas * 12 // 10 + 10000,
                "gasPrice": chain.w3.eth.gas_price,
            }
        )
        raw = account.sign_transaction(transaction)
        tx_hash = Web3.to_hex(raw.hash)
        body.update(
            approval={k: str(v) if isinstance(v, int) else v for k, v in approval.items()},
            tx_hash=tx_hash,
            signed=True,
            relayer=account.address,
            broadcast=False,
            calldata_hash=Web3.to_hex(Web3.keccak(hexstr=transaction["data"])),
        )
        # Durable exact signed bytes before the first broadcast, never create a replacement on retry.
        with self.runtime.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS payment_raw(id TEXT PRIMARY KEY,tx_hash TEXT NOT NULL,raw TEXT NOT NULL)"
            )
            db.execute(
                "INSERT INTO payment_raw VALUES (?,?,?)",
                (request.request_id, tx_hash, Web3.to_hex(raw.raw_transaction)),
            )
        with self.store.connection(write=True) as db:
            self.task(db, task.task_id, task.revision)
            db.execute(
                "UPDATE payments SET status='SUBMITTING',body=? WHERE id=?",
                (json.dumps(body), request.request_id),
            )
        try:
            chain.w3.eth.send_raw_transaction(raw.raw_transaction)
        except Exception:
            return self.save(request.request_id, "PENDING", body)
        body["broadcast"] = True
        self.save(request.request_id, "PENDING", body)
        return self.reconcile(request.request_id)

    def reconcile(self, id_):
        chain = self.local()
        result = self.read(id_)
        if not result.get("tx_hash"):
            return result
        try:
            receipt = chain.w3.eth.get_transaction_receipt(result["tx_hash"])
        except Exception:
            return self.save(
                id_,
                "PENDING",
                {k: v for k, v in result.items() if k not in {"status", "request_id"}},
            )
        body = {k: v for k, v in result.items() if k not in {"status", "request_id"}}
        if chain.w3.eth.get_block(receipt.blockNumber).hash != receipt.blockHash:
            body["reason_codes"] = ["TRANSFER_REORG"]
            return self.save(id_, "RECEIPT_MISMATCH", body)
        if (
            chain.w3.eth.block_number - receipt.blockNumber + 1
            < chain.settings.required_confirmations
        ):
            return self.save(id_, "PENDING", body)
        a = body["approval"]
        body["receipt"] = {
            "tx_hash": result["tx_hash"],
            "block_hash": Web3.to_hex(receipt.blockHash),
            "block_number": receipt.blockNumber,
            "status": receipt.status,
            "gas_used": str(receipt.gasUsed),
            "gas_cost_wei": str(receipt.gasUsed * receipt.effectiveGasPrice),
        }
        if not receipt.status:
            return self.save(id_, "REVERTED", body)
        events = chain.vault.events.ApprovedTransferExecuted().process_receipt(
            receipt, errors=DISCARD
        )
        expected = [
            e
            for e in events
            if e["address"].lower() == chain.vault.address.lower()
            and e["args"]["nonce"] == int(a["nonce"])
            and Web3.to_hex(e["args"]["intentHash"]) == a["intentHash"]
            and Web3.to_hex(e["args"]["taskHash"]) == a["taskHash"]
            and e["args"]["token"].lower() == a["token"].lower()
            and e["args"]["recipient"].lower() == a["recipient"].lower()
            and e["args"]["amount"] == int(a["amount"])
            and Web3.to_hex(e["args"]["evidenceRoot"]) == a["evidenceRoot"]
        ]
        tx = chain.w3.eth.get_transaction(result["tx_hash"])
        if (
            len(expected) != 1
            or Web3.to_hex(Web3.keccak(tx["input"])) != body["calldata_hash"]
            or tx["from"].lower() != body["relayer"].lower()
            or tx["to"].lower() != chain.vault.address.lower()
        ):
            return self.save(id_, "RECEIPT_MISMATCH", body)
        asset = self.execution.token_contract(chain.w3, "MockUSDC", a["token"])
        body["portfolio"] = {
            "block_number": receipt.blockNumber,
            "vault_balance": str(
                asset.functions.balanceOf(chain.vault.address).call(
                    block_identifier=receipt.blockNumber
                )
            ),
            "recipient_balance": str(
                asset.functions.balanceOf(Web3.to_checksum_address(a["recipient"])).call(
                    block_identifier=receipt.blockNumber
                )
            ),
            "transferred_base_units": a["amount"],
            "token": a["token"],
            "recipient": a["recipient"],
        }
        return self.save(id_, "CONFIRMED", body)
