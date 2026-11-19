from treasury_backend.core.errors import ControlError
from treasury_backend.modules import alignment as alignment
from treasury_backend.modules import decision as sde
from treasury_backend.modules import experience as experience
from treasury_backend.modules import planning as planner
from treasury_backend.modules import portfolio as portfolio
from treasury_backend.modules import proof as proof_service
from treasury_backend.modules import risk as economic_risk
from treasury_backend.modules.workflows.client import VerifiedExecutionClient
from treasury_backend.modules.workflows.evidence import verify_build
from treasury_backend.modules.workflows.mock import MockExecutionClient

STAGES = {
    "APPROVE": "APPROVED",
    "REPLAN": "REPLAN_REQUIRED",
    "REJECT": "REJECTED",
    "ESCALATE": "ESCALATED",
}


class EvaluationPipeline:
    def _run_attempts(self, workflow_id, mandate, client, goal):
        # Resolve the remote plan before opening the 30-second approval window.
        plan = self.planner.parse(goal)
        if self.settings.planning.provider in {"rotate", "gemini", "xingchi"}:
            provider = self.planner.provider
            self.store.event(
                workflow_id, "PLANNED", self.clock(),
                planner_provider=provider.last_provider, planner_model=provider.last_model,
                provider_attempts=list(provider.last_attempts),
            )
        amount = plan.amount
        fixture = client.fixture if isinstance(client, MockExecutionClient) else {}
        for index in range(mandate.max_replans + 1):
            now = self.clock()
            context = (
                self._tool(workflow_id, "read_chain_context", {}, client.context)
                if isinstance(client, VerifiedExecutionClient)
                else None
            )
            deadline = self._deadline(mandate, now, context)
            proposed = planner.propose(
                mandate,
                amount,
                deadline,
                alternate_recipient=fixture.get("poisoned_recipient"),
                reverse=plan.reverse,
            )
            self.store.event(
                workflow_id, "PROPOSED", now, attempt=index + 1, proposal=proposed.model_dump()
            )
            proposed, aligned = self._shield_plan(
                workflow_id, mandate, client, goal, proposed, amount, deadline, fixture
            )
            self.store.event(
                workflow_id, aligned.verdict, self.clock(), alignment=aligned.model_dump()
            )
            decision = self._evaluate(workflow_id, mandate, client, proposed, aligned, context)
            runtime = self.shield_runtimes.get(workflow_id)
            if runtime:
                for shield_retry in range(self.settings.shield.max_replans):
                    feedback = runtime.last_feedback
                    if feedback is None or feedback.code == "TASK_SHIELD_UNAVAILABLE":
                        break
                    self.shield.state.event(
                        runtime.session_id,
                        "REPLAN_AFTER_TOOL_OUTPUT",
                        self.clock(),
                        {
                            "retry": shield_retry + 1,
                            "feedback": feedback.model_dump(mode="json"),
                            "previous_decision_id": decision.decision_id,
                        },
                    )
                    # The original candidate and rejected tool output are never reused as executable instructions.
                    proposed = planner.revise(
                        mandate, amount, self._deadline(mandate, self.clock(), context), feedback,
                        reverse=proposed.token_in == mandate.token_out,
                    )
                    runtime.last_feedback = None
                    proposed, aligned = self._shield_plan(
                        workflow_id, mandate, client, goal, proposed, amount, proposed.deadline, {}
                    )
                    decision = self._evaluate(
                        workflow_id, mandate, client, proposed, aligned, context
                    )
                if runtime.last_feedback:
                    self.shield.state.event(
                        runtime.session_id,
                        "SHIELD_STOPPED",
                        self.clock(),
                        {
                            "feedback": runtime.last_feedback.model_dump(mode="json"),
                            "decision_id": decision.decision_id,
                        },
                    )
                    if decision.verdict == "APPROVE":
                        self.store.event(
                            workflow_id,
                            "ESCALATED",
                            self.clock(),
                            reason_codes=["TASK_SHIELD_FEEDBACK_PENDING"],
                            decision_id=decision.decision_id,
                        )
                    return
            if decision.verdict == "APPROVE":
                signed = self.attest(decision.decision_id)
                self._submit(workflow_id, decision, signed)
                return
            if decision.verdict != "REPLAN" or index >= mandate.max_replans:
                return
            replacement = experience.next_amount(self.store, workflow_id, amount)
            if replacement is None:
                return
            amount = replacement

    def _evaluate(self, workflow_id, mandate, client, proposal, aligned, context=None):
        built = sim = evaluation = balances = snapshot = observation = None
        proof = None
        issues = []
        try:
            context = context or self._tool(workflow_id, "read_chain_context", {}, client.context)
            issues = portfolio.policy_issues(mandate, context, self.clock())
            if aligned.verdict == "ALIGNED" and not issues:
                self.require_priced_assets(mandate)
                reverse = proposal.token_in.lower() == mandate.token_out
                cap = (
                    mandate.proof_policy.max_wavax_per_swap
                    if reverse and mandate.proof_policy
                    else mandate.max_usdc_per_swap_base_units
                )
                if int(proposal.amount_in_base_units) > int(cap):
                    # The builder may enforce the same cap before simulation.
                    issues.append("TRADE_SIZE_LIMIT")
                    raise ControlError("TRADE_SIZE_LIMIT")
                built = self._tool(
                    workflow_id, "build_swap", proposal.model_dump(), lambda: client.build(proposal)
                )
                verify_build(mandate, proposal, built)
                self.store.event(workflow_id, "BUILT", self.clock(), build=built.model_dump())
                sim = self._tool(
                    workflow_id,
                    "simulate_swap",
                    {"build": built.model_dump()},
                    lambda: client.simulate(built),
                )
                balances = self._tool(workflow_id, "read_portfolio", {}, client.balances)
                context = self._tool(
                    workflow_id,
                    "read_chain_context",
                    {"build_id": built.build_id, "fork_block": sim.fork_block},
                    lambda: client.context(built=built, fork_block=sim.fork_block),
                )
                issues = self.verify_evidence(client, built, sim, context, workflow_id)
                observation = self._tool(
                    workflow_id,
                    "observe_portfolio",
                    {"vault_address": mandate.vault_address, "block_number": balances.block_number},
                    lambda: self.observe(
                        client,
                        mandate,
                        balances,
                        context,
                        workflow_id=workflow_id,
                        built=built,
                        phase="PRE",
                    ),
                )
                self.store.event(
                    workflow_id,
                    "SIMULATED",
                    self.clock(),
                    simulation=sim.model_dump(),
                    provenance="UNVERIFIED" if issues else "VERIFIED",
                )
                if not issues:
                    self.require_priced_assets(mandate)
                    snapshot = portfolio.decision_snapshot(
                        observation, balances, self.price(client, sim.fork_block), context, built, self.clock()
                    )
                    evaluation = economic_risk.evaluate(
                        mandate, proposal, built, sim, snapshot, balances, context, self.clock()
                    )
                    if mandate.proof_policy is not None and evaluation.risk.result == "PASS":
                        proof = proof_service.prove(
                            mandate,
                            built,
                            sim,
                            snapshot,
                            context,
                            self.clock(),
                            self.store.proof_query,
                        )
        except ControlError as error:
            issues.append(
                "TRADE_SIZE_LIMIT"
                if error.code in {"DAILY_SPEND_LIMIT", "INSUFFICIENT_BALANCE"}
                else error.code
            )
            if error.code in {"DAILY_SPEND_LIMIT", "INSUFFICIENT_BALANCE"}:
                try:
                    balances = client.balances()
                except ControlError as balance_error:
                    issues.append(balance_error.code)

        decision = sde.decide(
            mandate,
            proposal,
            aligned,
            context,
            self.clock(),
            built=built,
            evidence=sim,
            risk=evaluation.risk if evaluation else None,
            provenance_issues=issues,
            proof=proof,
        )
        suggested = evaluation.suggested_amount if evaluation else 0
        if decision.verdict == "REPLAN" and not evaluation and "TRADE_SIZE_LIMIT" in issues:
            reverse = proposal.token_in.lower() == mandate.token_out
            direction_cap = (
                int(mandate.proof_policy.max_wavax_per_swap)
                if reverse and mandate.proof_policy
                else int(mandate.max_usdc_per_swap_base_units)
            )
            suggested = min(direction_cap, int(proposal.amount_in_base_units) - 1)
            if balances is not None:
                suggested = min(
                    suggested,
                    int(balances.wavax_base_units if reverse else balances.usdc_base_units),
                    direction_cap
                    if reverse
                    else max(
                        0,
                        int(mandate.max_usdc_spend_per_day_base_units)
                        - int(balances.daily_spent_usdc_base_units),
                    ),
                )
        evidence = (
            {
                "risk": evaluation.risk.model_dump(),
                "portfolio": snapshot.model_dump(),
                "chain_balances": balances.model_dump(),
            }
            if evaluation
            else {}
        )
        self.store.record(
            workflow_id,
            STAGES[decision.verdict],
            decision,
            {
                "mode": self.settings.mode,
                "decision": decision.model_dump(),
                "mandate": mandate.model_dump(),
                "proposal": proposal.model_dump(),
                "alignment": aligned.model_dump(),
                "build": built.model_dump() if built else None,
                "simulation": sim.model_dump() if sim else None,
                "suggested_amount": suggested,
                **({"proof": proof.model_dump(mode="json")} if proof else {}),
                "chain_context": context.model_dump() if context else None,
                "pre_snapshot_id": observation.snapshot_id if observation else None,
                "task_shield_proof": self.shield_runtimes[workflow_id].proof(proposal)
                if workflow_id in self.shield_runtimes
                else None,
                **evidence,
            },
            suggested,
            evidence,
        )
        if observation:
            self.store.save_snapshot(
                observation,
                phase="PRE",
                workflow_id=workflow_id,
                decision_id=decision.decision_id,
                build_id=built.build_id if built else None,
            )
        return decision
