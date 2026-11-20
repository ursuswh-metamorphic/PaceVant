from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_task_shield import QueueProvider, setup, user

from treasury_backend.config.control import Settings
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.alignment.runtime import ShieldRuntime
from treasury_backend.modules.workflows.service import ControlPlane
from treasury_contracts.toolchain import native_tool_environment


def test_failed_batch_budget_keeps_every_uninspected_record(tmp_path):
    shield, _ = setup(tmp_path, QueueProvider(), max_output_chars=1000)
    shield.config = replace(shield.config, mode="wallet_pipeline")
    runtime = ShieldRuntime(shield, "session_a")
    runtime.defer_data("read_simulation_artifact", {}, {"text": "x" * 2000})
    with pytest.raises(ControlError, match="TASK_SHIELD_OUTPUT_BUDGET"):
        runtime.flush_data()
    assert len(runtime.pending_outputs) == 1
    with pytest.raises(ControlError, match="TASK_SHIELD_UNINSPECTED_EVIDENCE"):
        runtime.proof({})


def test_successful_output_check_is_bound_into_approval_proof(tmp_path):
    shield, _ = setup(tmp_path, QueueProvider('["Swap 10 USDC"]', "[]"))
    shield.config = replace(shield.config, mode="wallet_pipeline")
    user(shield, "Swap 10 USDC")
    runtime = ShieldRuntime(shield, "session_a")
    runtime.defer_data("read_chain_context", {}, {"block": 1})
    runtime.flush_data()
    proof = runtime.proof({})
    assert len(proof["check_ids"]) == 1 and not runtime.pending_outputs
    record = shield.state.check_record(proof["check_ids"][0])
    assert record["source"] == "TOOL" and record["status"] == "ALIGNED"
    shield.validate(proof["session_id"], proof["check_ids"], proof["revision"])


@pytest.mark.parametrize("factory", [None, lambda *args: SimpleNamespace(fixture_mode=True)])
def test_live_execution_never_falls_back_to_fixture_client(factory):
    service = SimpleNamespace(
        settings=SimpleNamespace(mode="FUJI"),
        client_factory=factory,
        http=None,
        store=None,
        mock_clients={},
    )
    with pytest.raises(
        ControlError,
        match="LIVE_FIXTURE_CLIENT_FORBIDDEN" if factory else "EXECUTION_CLIENT_UNAVAILABLE",
    ):
        ControlPlane.client(service, "workflow", None)


def test_approval_deadline_cannot_exceed_session_expiry():
    now = 2_000_000_000
    context = SimpleNamespace(
        max_approval_ttl=300,
        block_timestamp=now,
        policy_expires_at=now + 10000,
        proof_session=SimpleNamespace(expires_at=now + 45),
    )
    assert ControlPlane._deadline(SimpleNamespace(expires_at=now + 20000), now, context) == now + 45


@pytest.mark.parametrize("value", ["true", "yes", "2", "1 "])
def test_invalid_required_itag_flag_does_not_disable_security(monkeypatch, value):
    monkeypatch.setenv("PACEVANT_MODE", "MOCK")
    monkeypatch.setenv("PACEVANT_REQUIRE_ITAG", value)
    with pytest.raises(RuntimeError, match="PACEVANT_REQUIRE_ITAG"):
        Settings.from_env()


def test_native_process_environment_excludes_all_service_credentials(monkeypatch):
    for key in (
        "DEEPSEEK_API_KEY",
        "GROQ_API_KEY",
        "PACEVANT_ATTESTOR_KEY",
        "B_RELAYER_PRIVATE_KEY",
        "DEPLOYER_PRIVATE_KEY",
        "CUSTOM_SECRET",
        "HTTPS_PROXY",
    ):
        monkeypatch.setenv(key, "must-not-reach-native-tool")
    environment = native_tool_environment()
    assert "PATH" in {key.upper() for key in environment}
    assert "must-not-reach-native-tool" not in environment.values()
