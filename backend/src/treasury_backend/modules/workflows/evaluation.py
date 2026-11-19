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
            context = client.context() if isinstance(client, VerifiedExecutionClient) else None
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
            aligned = alignment.check(mandate, proposed, goal, fixture.get("tool_output", ""))
            self.store.event(
                workflow_id, aligned.verdict, self.clock(), alignment=aligned.model_dump()
            )
            decision = self._evaluate(workflow_id, mandate, client, proposed, aligned, context)
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
        built = sim = evaluation = balances = snapshot = None
        proof = None
        issues = []
        try:
            context = context or client.context()
            issues = portfolio.policy_issues(mandate, context, self.clock())
            if aligned.verdict == "ALIGNED" and not issues:
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
                built = client.build(proposal)
                verify_build(mandate, proposal, built)
                self.store.event(workflow_id, "BUILT", self.clock(), build=built.model_dump())
                sim = client.simulate(built)
                balances = client.balances()
                context = client.context(built=built, fork_block=sim.fork_block)
                issues = self.verify_evidence(client, built, sim, context)
                self.store.event(
                    workflow_id,
                    "SIMULATED",
                    self.clock(),
                    simulation=sim.model_dump(),
                    provenance="UNVERIFIED" if issues else "VERIFIED",
                )
                if not issues:
                    self.require_priced_assets(mandate)
                    snapshot = portfolio.snapshot(
                        balances, self.price(client, sim.fork_block), self.store.history_version()
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
                **evidence,
            },
            suggested,
            evidence,
        )
        return decision
