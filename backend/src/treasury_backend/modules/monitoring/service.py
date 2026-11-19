"""Bounded reconciliation. No execute, signing, deployment or rebroadcast path exists here."""

import json
import time
from uuid import uuid4

from treasury_backend.core.domain import ObservedPortfolioSnapshot
from treasury_backend.core.errors import ControlError
from treasury_backend.core.models import ChainBalances, ChainContext, Mandate
from treasury_backend.modules import portfolio
from treasury_contracts.models import (
    BuiltTransaction,
    ExecutionReconciliation,
    ExecutionResult,
    SimulationEvidence,
)
from treasury_contracts.outcomes_v2 import parse_pdr
from treasury_contracts.readonly import readonly_web3


class OutcomeMonitor:
    def __init__(self, store, mode, client_factory, clock=time.time):
        self.store, self.mode, self.client_factory, self.clock = store, mode, client_factory, clock

    def bootstrap(self):
        # Add jobs for legacy durable submissions without rewriting original evidence.
        with self.store.connection() as conn:
            rows = conn.execute(
                "SELECT a.decision_id,d.workflow_id,d.body FROM attestations a JOIN decisions d ON d.id=a.decision_id JOIN workflows w ON w.id=d.workflow_id WHERE json_extract(w.body,'$.mode')=? AND a.state IN ('SUBMITTING','SUBMITTED','CONFIRMED','REVERTED','RECEIPT_MISMATCH') AND NOT EXISTS(SELECT 1 FROM monitor_jobs j WHERE j.decision_id=a.decision_id) ORDER BY a.rowid LIMIT 50",
                (self.mode,),
            ).fetchall()
        for row in rows:
            bundle = json.loads(row["body"])
            built = BuiltTransaction.model_validate(bundle["build"])
            wf = self.store.workflow(row["workflow_id"])
            tx = next(
                (
                    e.get("tx_hash") or (e.get("receipt") or {}).get("tx_hash")
                    for e in reversed(wf["timeline"])
                    if e.get("tx_hash") or (e.get("receipt") or {}).get("tx_hash")
                ),
                None,
            )
            self.store.track_execution(
                row["workflow_id"], row["decision_id"], self.mode, built, int(self.clock()), tx
            )

    def tick(self, *, limit=10):
        self.bootstrap()
        ids = self.store.due_monitors(self.mode, int(self.clock()), limit)
        return [self.process(id_) for id_ in ids]

    def _pre(self, bundle, client, context, job, mandate, built):
        if bundle.get("pre_snapshot_id"):
            return ObservedPortfolioSnapshot.model_validate(
                self.store.snapshot_record(bundle["pre_snapshot_id"])["snapshot"]
            )
        # Explicit legacy reconstruction from chain data at the originally recorded height.
        balances = ChainBalances.model_validate(bundle["chain_balances"])
        version = self.store.history_version(built.chain_id, built.vault_address, self.mode)
        if getattr(client, "fixture_mode", False):
            value = portfolio.fixture_observation(balances, context, version, int(self.clock()))
        else:
            value = client.observe(
                mandate, block_number=balances.block_number, history_version=version
            )
            if (value.assets[1].balance_base_units, value.assets[2].balance_base_units) != (
                balances.usdc_base_units,
                balances.wavax_base_units,
            ):
                raise ControlError("LEGACY_PRESTATE_MISMATCH")
        self.store.save_snapshot(
            value,
            phase="LEGACY_RECONSTRUCTED_PRE",
            workflow_id=job["workflow_id"],
            decision_id=job["decision_id"],
            build_id=built.build_id,
        )
        return value

    def _mock_report(self, client, built, pdr, tx_hash, receipt):
        if receipt.status in {"PENDING", "SUBMITTED"}:
            return ExecutionReconciliation(
                chain_id=built.chain_id,
                vault_address=built.vault_address,
                build_id=built.build_id,
                decision_id=pdr.decision_id,
                tx_hash=tx_hash,
                typed_data_hash=pdr.typed_data_hash,
                observed_at=int(self.clock()),
                verification_status="PENDING",
                receipt_status="PENDING",
            )
        problems = []
        if (receipt.tx_hash, receipt.decision_id, receipt.build_id, receipt.chain_id) != (
            tx_hash,
            pdr.decision_id,
            built.build_id,
            built.chain_id,
        ):
            problems.append("TRANSACTION_BUILD_MISMATCH")
        if receipt.block_number is None or receipt.gas_used is None:
            problems.append("RECEIPT_EVIDENCE_MISSING")
        if receipt.status == "CONFIRMED":
            if (
                receipt.actual_token_in_delta_base_units != f"-{built.amount_in_base_units}"
                or int(receipt.actual_token_out_delta_base_units or "0")
                < int(built.min_amount_out_base_units)
                or not receipt.event_refs
                or receipt.revert_reason
            ):
                problems.append("RECEIPT_MISMATCH")
        elif (
            receipt.status != "REVERTED"
            or receipt.actual_token_in_delta_base_units != receipt.actual_token_out_delta_base_units
            or receipt.actual_token_out_delta_base_units != "0"
        ):
            problems.append("RECEIPT_MISMATCH")
        context = client.context(built=built)
        return ExecutionReconciliation(
            chain_id=built.chain_id,
            vault_address=built.vault_address,
            build_id=built.build_id,
            decision_id=pdr.decision_id,
            tx_hash=tx_hash,
            typed_data_hash=pdr.typed_data_hash,
            observed_at=int(self.clock()),
            verification_status="MISMATCH" if problems else "VERIFIED",
            receipt_status="SUCCESS" if receipt.status == "CONFIRMED" else "REVERTED",
            reason_codes=problems,
            canonical=not problems,
            block_number=receipt.block_number,
            block_hash=client.block_hash(receipt.block_number)
            if receipt.block_number is not None
            else None,
            block_timestamp=int(self.clock()),
            head_block=context.block_number,
            confirmations=1,
            finality_confidence="INCLUDED",
            gas_used=receipt.gas_used,
            effective_gas_price_wei="25000000000",
            gas_cost_wei=str(int(receipt.gas_used or "0") * 25_000_000_000),
            gas_verified=not problems,
            gas_payer=context.relayer,
            gas_payer_role="RELAYER",
            nonce_used=context.nonce_used,
            token_in_delta_base_units=receipt.actual_token_in_delta_base_units,
            token_out_delta_base_units=receipt.actual_token_out_delta_base_units,
            allowances={"vault_to_adapter": "0"},
        )

    def process(self, id_, *, force=False, client=None, receipt=None):
        now = int(self.clock())
        owner = uuid4().hex
        job = self.store.claim_monitor(id_, owner, now, force=force)
        if not job:
            return {"decision_id": id_, "state": "BUSY_OR_NOT_DUE"}
        state = "UNAVAILABLE"
        details = {"decision_id": id_, "reason_codes": ["MONITOR_UNAVAILABLE"]}
        try:
            _, bundle = self.store.decision(decision_id=id_)
            mandate = Mandate.model_validate(bundle["mandate"])
            built = BuiltTransaction.model_validate(bundle["build"])
            with self.store.connection() as conn:
                row = conn.execute(
                    "SELECT signed_pdr FROM attestations WHERE decision_id=?", (id_,)
                ).fetchone()
            pdr = parse_pdr(row[0])
            client = client or self.client_factory(job["workflow_id"], mandate)
            if not job["tx_hash"]:
                found = (
                    client.submission_for_build(built.build_id)
                    if hasattr(client, "submission_for_build")
                    else None
                )
                if not found:
                    state = (
                        "EXPIRED_UNESTABLISHED" if now > built.deadline else "UNKNOWN_SUBMISSION"
                    )
                    details = {
                        "state": state,
                        "decision_id": id_,
                        "observed_at": now,
                        "reason_codes": ["SUBMISSION_OUTCOME_NOT_ESTABLISHED"],
                    }
                    self.store.record_poll(job, now, details)
                    return details
                job["tx_hash"] = found.tx_hash
                self.store.track_execution(
                    job["workflow_id"], id_, self.mode, built, now, found.tx_hash
                )
                self.store.transition(
                    job["workflow_id"], id_, "SUBMITTING", "SUBMITTED", now, tx_hash=found.tx_hash
                )
            context = (
                ChainContext.model_validate(bundle["chain_context"])
                if bundle.get("chain_context")
                else client.context(built=built)
            )
            if getattr(client, "fixture_mode", False):
                receipt = receipt or client.execution(job["tx_hash"])
                report = self._mock_report(client, built, pdr, job["tx_hash"], receipt)
            else:
                evidence = SimulationEvidence.model_validate(bundle["simulation"])
                report = client.reconciliation(
                    built, pdr, job["tx_hash"], context=context, evidence=evidence
                )
                receipt = ExecutionResult(
                    build_id=built.build_id,
                    decision_id=id_,
                    chain_id=built.chain_id,
                    tx_hash=job["tx_hash"],
                    status="CONFIRMED"
                    if report.receipt_status == "SUCCESS"
                    else "REVERTED"
                    if report.receipt_status == "REVERTED"
                    else "PENDING",
                    block_number=report.block_number,
                    block_hash=report.block_hash,
                    confirmations=report.confirmations,
                    proof_session=report.proof_session,
                    gas_used=report.gas_used,
                    actual_token_in_delta_base_units=report.token_in_delta_base_units,
                    actual_token_out_delta_base_units=report.token_out_delta_base_units,
                    event_refs=["SwapExecuted"] if report.swap_events else [],
                    artifact_refs=report.artifact_refs,
                )
            previous = self.store.outcome_projection(id_)
            invalidate = False
            if (
                previous
                and previous["verification"].get("block_hash")
                and not getattr(client, "fixture_mode", False)
            ):
                old = previous["verification"]
                reader = readonly_web3(client.settings.chain_rpc_url, built.chain_id)
                try:
                    canonical_hash = reader.eth.get_block(old["block_number"]).hash.hex()
                    canonical_hash = "0x" + canonical_hash.removeprefix("0x")
                finally:
                    reader.provider.close()
                invalidate = canonical_hash != old["block_hash"]
            if report.verification_status in {"PENDING", "UNAVAILABLE"} and not invalidate:
                state = report.verification_status
                details = {"state": state, "decision_id": id_, "verification": report.model_dump()}
                self.store.record_poll(job, now, details)
                return details
            if invalidate and report.verification_status in {"PENDING", "UNAVAILABLE"}:
                report = report.model_copy(
                    update={
                        "verification_status": "REORGED",
                        "canonical": False,
                        "gas_verified": False,
                        "reason_codes": ["REORG_DETECTED"],
                    }
                )
            pre = post = None
            reasons = list(report.reason_codes)
            residual = {}
            attribution = "UNESTABLISHED"
            if report.canonical:
                try:
                    pre = self._pre(bundle, client, context, job, mandate, built)
                    if pre.verification_status != "VERIFIED" and not (
                        pre.mode == "MOCK" and pre.reason_codes == ["MOCK_NATIVE_NOT_MODELED"]
                    ):
                        raise ControlError("PRE_SNAPSHOT_UNVERIFIED")
                    if not getattr(client, "fixture_mode", False):
                        reader = readonly_web3(client.settings.chain_rpc_url, built.chain_id)
                        try:
                            if (
                                "0x"
                                + reader.eth.get_block(pre.block_number)
                                .hash.hex()
                                .removeprefix("0x")
                                != pre.block_hash
                            ):
                                self.store.invalidate_snapshot(pre.snapshot_id, now)
                                raise ControlError("PRE_SNAPSHOT_REORGED")
                        finally:
                            reader.provider.close()
                    version = self.store.history_version(
                        built.chain_id, built.vault_address, self.mode
                    )
                    if (
                        previous
                        and not invalidate
                        and previous.get("post_snapshot_id")
                        and previous["verification"].get("block_hash") == report.block_hash
                    ):
                        post = ObservedPortfolioSnapshot.model_validate(
                            self.store.snapshot_record(previous["post_snapshot_id"])["snapshot"]
                        )
                    elif getattr(client, "fixture_mode", False):
                        balances = client.balances()
                        post = portfolio.fixture_observation(
                            balances, client.context(), version, now
                        )
                    else:
                        post = client.observe(
                            mandate, block_number=report.block_number, history_version=version
                        )
                    self.store.save_snapshot(
                        post,
                        phase="POST_OBSERVED",
                        workflow_id=job["workflow_id"],
                        decision_id=id_,
                        build_id=built.build_id,
                        tx_hash=job["tx_hash"],
                    )
                    if (
                        post.block_number != report.block_number
                        or post.block_hash != report.block_hash
                    ):
                        raise ControlError("POST_SNAPSHOT_BLOCK_MISMATCH")
                    before = {a.asset_id: a for a in pre.assets}
                    after = {a.asset_id: a for a in post.assets}
                    expected = {
                        f"{built.chain_id}:erc20:{built.token_in.lower()}": report.token_in_delta_base_units,
                        f"{built.chain_id}:erc20:{built.token_out.lower()}": report.token_out_delta_base_units,
                    }
                    for asset_id, asset in after.items():
                        prior = before.get(asset_id)
                        if (
                            not prior
                            or prior.balance_base_units is None
                            or asset.balance_base_units is None
                        ):
                            if asset.contract is not None:
                                raise ControlError("RECONCILIATION_BALANCE_UNAVAILABLE")
                            continue
                        actual = int(asset.balance_base_units) - int(prior.balance_base_units)
                        target = expected.get(asset_id, "0")
                        if target is None:
                            raise ControlError("TRANSACTION_DELTA_UNVERIFIED")
                        if actual != int(target):
                            residual[asset_id] = str(actual - int(target))
                    if residual:
                        reasons.append("EXTERNAL_ACTIVITY_OR_ATTRIBUTION_MISMATCH")
                        attribution = "INCONCLUSIVE_EXTERNAL_DELTA"
                    else:
                        attribution = "EXACT_SNAPSHOT_AND_TRANSACTION_LOGS"
                    if post.verification_status != "VERIFIED" and post.reason_codes != [
                        "MOCK_NATIVE_NOT_MODELED"
                    ]:
                        reasons.append("POST_SNAPSHOT_UNVERIFIED")
                except ControlError as error:
                    reasons.append(error.code)
            state = "CONFIRMED" if report.receipt_status == "SUCCESS" else "REVERTED"
            if report.verification_status != "VERIFIED" or reasons:
                state = "RECEIPT_MISMATCH"
            details = {
                "workflow_id": job["workflow_id"],
                "decision_id": id_,
                "build_id": built.build_id,
                "intent_id": built.intent_id,
                "mandate_id": mandate.mandate_id,
                "policy_hash": built.policy_hash,
                "policy_version": context.policy_version,
                "simulation_evidence_root": bundle["simulation"]["evidence_root"],
                "pdr_ref": pdr.typed_data_hash,
                "verification": report.model_dump(),
                "receipt": receipt.model_dump(),
                "pre_snapshot_id": pre.snapshot_id if pre else None,
                "post_snapshot_id": post.snapshot_id if post else None,
                "attribution_status": attribution,
                "unattributed_balance_deltas": residual,
                "reason_codes": list(dict.fromkeys(reasons)),
                "planned_token_in_base_units": built.amount_in_base_units,
                "planned_min_out_base_units": built.min_amount_out_base_units,
                "gas_accounting": "RELAYER_OPERATIONAL_EXPENSE_NOT_TREASURY_TOKEN_DEBIT",
                "state": state,
                "risk": bundle.get("risk"),
            }
            if post:
                details["post_execution_balances"] = {
                    "chain_id": post.chain_id,
                    "vault_address": post.vault_address,
                    "block_number": post.block_number,
                    "usdc_base_units": post.assets[1].balance_base_units,
                    "wavax_base_units": post.assets[2].balance_base_units,
                }
            self.store.commit_outcome(
                job,
                owner,
                now,
                details,
                state,
                pre_id=pre.snapshot_id if pre else None,
                post_id=post.snapshot_id if post else None,
                invalidate=invalidate or report.verification_status == "REORGED",
            )
            return details
        except (ControlError, ValueError, KeyError, TypeError) as error:
            details = {
                "decision_id": id_,
                "state": "UNAVAILABLE",
                "reason_codes": [
                    error.code if isinstance(error, ControlError) else "MONITOR_DATA_UNAVAILABLE"
                ],
            }
            self.store.record_poll(job, now, details)
            return details
        except Exception:
            details = {
                "decision_id": id_,
                "state": "UNAVAILABLE",
                "reason_codes": ["MONITOR_RPC_UNAVAILABLE"],
            }
            self.store.record_poll(job, now, details)
            return details
        finally:
            self.store.release_monitor(id_, owner, now, state, details)
