import json
from typing import Protocol

import httpx
import rfc8785
from pydantic import ValidationError

from app.attestor.typed import hash_bytes
from app.errors import ControlError
from app.models import ChainContext, EvidenceReport, Mandate, Manifest, Mode
from app.portfolio import fresh
from treasury_contracts.models import BuiltTransaction, SimulationEvidence, TransactionProposal

SOURCES = {"MOCK": "MOCK_FIXTURE", "LOCAL": "REAL_LOCAL_SIM", "FUJI": "FORK_SIM"}
MANIFEST_FIELDS = (
    "chain_id",
    "vault_address",
    "policy_hash",
    "calldata_hash",
    "fork_block",
    "bytecode_hash",
    "parser_version",
    "verification_status",
)
REPORT_FIELDS = (
    "intent_id",
    "build_id",
    "nonce",
    "deadline",
    "simulation_mode",
    "source",
    "baseline",
    "stress_tests",
)


class Artifacts(Protocol):
    def artifact(self, reference: str) -> bytes: ...


class InvalidJSON(ValueError):
    pass


def json_object(raw: bytes) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InvalidJSON("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
    if not isinstance(value, dict):
        raise InvalidJSON("expected a JSON object")
    return value


def verify_build(mandate: Mandate, proposal: TransactionProposal, built: BuiltTransaction):
    if built.router.lower() != mandate.router:
        raise ControlError("ROUTER_NOT_ALLOWED")
    pair = (built.token_in.lower(), built.token_out.lower())
    if pair != (mandate.token_in, mandate.token_out) and not (
        mandate.proof_policy is not None and pair == (mandate.token_out, mandate.token_in)
    ):
        raise ControlError("TOKEN_NOT_ALLOWED")
    fields = (
        "intent_id",
        "chain_id",
        "amount_in_base_units",
        "deadline",
    )
    if (
        any(getattr(proposal, field) != getattr(built, field) for field in fields)
        or proposal.vault_address.lower() != built.vault_address.lower()
        or proposal.router.lower() != built.router.lower()
        or proposal.token_in.lower() != built.token_in.lower()
        or proposal.token_out.lower() != built.token_out.lower()
        or built.policy_hash != mandate.policy_hash
        or hash_bytes(bytes.fromhex(built.router_calldata[2:])) != built.calldata_hash
    ):
        raise ControlError("HASH_MISMATCH")


def evidence_issues(
    client: Artifacts,
    mode: Mode,
    built: BuiltTransaction,
    sim: SimulationEvidence,
    context: ChainContext,
    now: int,
) -> list[str]:
    if sim.source != SOURCES[mode] or context.deployment != mode:
        return ["UNVERIFIED_SIMULATION_SOURCE"]
    if mode != "MOCK":
        try:
            manifest = client.verify_evidence(built, sim)
            timestamp = manifest["timestamp"]
            if (
                context.fork_block != sim.fork_block
                or context.fork_block_hash != manifest["fork_block_hash"]
                or type(timestamp) is not int
                or context.fork_block_timestamp != timestamp
                or timestamp > context.block_timestamp
            ):
                return ["HASH_MISMATCH"]
            return [] if fresh(timestamp, now) else ["SIMULATION_INCOMPLETE"]
        except (ControlError, httpx.HTTPError):
            return ["SIMULATION_INCOMPLETE"]
        except (ValueError, KeyError, TypeError, RecursionError):
            return ["HASH_MISMATCH"]
    fields = (
        "build_id",
        "intent_id",
        "chain_id",
        "vault_address",
        "policy_hash",
        "calldata_hash",
        "nonce",
        "deadline",
    )
    if any(getattr(sim, field) != getattr(built, field) for field in fields):
        return ["HASH_MISMATCH"]
    try:
        raw_manifest = json_object(client.artifact(sim.evidence_manifest_ref))
        manifest = Manifest.model_validate(raw_manifest)
        if (
            hash_bytes(rfc8785.dumps(raw_manifest)) != sim.evidence_root
            or any(getattr(manifest, key) != getattr(sim, key) for key in MANIFEST_FIELDS)
            or set(manifest.artifact_hashes) != set(sim.artifact_refs)
            or len(sim.artifact_refs) != len(manifest.artifact_hashes)
            or sim.evidence_manifest_ref in manifest.artifact_hashes
            or context.fork_block != sim.fork_block
            or context.fork_block_hash != manifest.fork_block_hash
            or context.fork_block_timestamp != manifest.fork_block_timestamp
            or manifest.fork_block_timestamp > context.block_timestamp
        ):
            return ["HASH_MISMATCH"]
        if not fresh(manifest.fork_block_timestamp, now):
            return ["SIMULATION_INCOMPLETE"]
        # The first artifact is the normalized evidence report. Auxiliary artifacts are
        # also content-addressed, so the manifest commits to the data SDE actually reads.
        for index, (ref) in enumerate(sim.artifact_refs):
            artifact = client.artifact(ref)
            if hash_bytes(artifact) != manifest.artifact_hashes[ref]:
                return ["HASH_MISMATCH"]
            if index == 0:
                report = EvidenceReport.model_validate(json_object(artifact))
                if any(getattr(report, key) != getattr(sim, key) for key in REPORT_FIELDS):
                    return ["HASH_MISMATCH"]
    except ControlError:
        return ["SIMULATION_INCOMPLETE"]
    except (ValidationError, ValueError, RecursionError):
        return ["HASH_MISMATCH"]
    return []
