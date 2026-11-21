"""Contract probes must retain identity, isolation and durable request semantics."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from treasury_backend.api.judge import create_app
from treasury_backend.config.judge import JudgeSettings
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.workflows.judge import JudgeController


def test_attack_identity_is_bound_to_idempotency_and_operation(tmp_path, monkeypatch):
    monkeypatch.setattr(JudgeSettings, "configured", lambda _: True)
    settings = JudgeSettings(data_dir=tmp_path, execution_mode="REAL_FUJI_EXECUTION", secure_cookie=False)
    controller = JudgeController(settings, runner=lambda *_: {"status": "REJECTED"})
    controller.start()
    try:
        first = controller.create("visitor", "ip", "payment", "attack-key", attack="payment-amount")
        controller.pool.shutdown(wait=True)
        assert controller.create("visitor", "ip", "payment", "attack-key", attack="payment-amount")["job_id"] == first["job_id"]
        for attack in (None, "payment-replay"):
            with pytest.raises(ControlError, match="IDEMPOTENCY_CONFLICT"):
                controller.create("visitor", "ip", "payment", "attack-key", attack=attack)
        with pytest.raises(ControlError, match="INVALID_ATTACK_SCENARIO"):
            controller.create("visitor", "ip", "swap", "other-key", attack="payment-amount")
        with pytest.raises(ControlError, match="INVALID_ATTACK_SCENARIO"):
            controller.create("visitor", "ip", "payment", "other-key", attack="arbitrary")
    finally:
        controller.close()


def test_cookie_slides_for_many_days_without_losing_history_on_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(JudgeSettings, "configured", lambda _: True)
    settings = JudgeSettings(data_dir=tmp_path, secure_cookie=False)
    controller = JudgeController(settings, runner=lambda *_: {"status": "REJECTED"})
    with TestClient(create_app(settings, controller=controller)) as client:
        first = client.get("/judge/config")
        assert "Max-Age=2592000" in first.headers["set-cookie"]
        cookie = client.cookies.get("pacevant_judge")
        result = client.post("/judge/jobs", json={"scenario": "guard"}, headers={"Idempotency-Key": "durable-request"}).json()
        controller.pool.shutdown(wait=True)
        assert client.get("/judge/history").json()["jobs"][0]["job_id"] == result["job_id"]
        assert client.cookies.get("pacevant_judge") == cookie
    later = JudgeController(settings, runner=lambda *_: pytest.fail("Must never resubmit"), clock=lambda: time.time()+5*86400)
    with TestClient(create_app(settings, controller=later)) as client:
        client.cookies.set("pacevant_judge", cookie)
        response = client.get("/judge/requests/durable-request")
        assert response.json()["job_id"] == result["job_id"]
        assert "Max-Age=2592000" in response.headers["set-cookie"]


def test_public_cleanup_never_removes_send_journals(tmp_path):
    settings = JudgeSettings(data_dir=tmp_path, execution_mode="REAL_FUJI_EXECUTION")
    controller = JudgeController(settings)
    directory = tmp_path / "runs" / "judge_old"
    directory.mkdir(parents=True)
    journal = directory / "send-journal.json"
    journal.write_text(json.dumps({"tx_hash": "public-evidence"}))
    controller.cleanup()
    assert journal.exists()
    controller.close()


def test_public_restart_retains_broadcast_evidence_without_resubmission(tmp_path):
    settings = JudgeSettings(data_dir=tmp_path, execution_mode="REAL_FUJI_EXECUTION")
    first = JudgeController(settings)
    value = {"job_id": "judge_old", "scenario": "payment", "status": "RUNNING", "terminal": False}
    with first.db() as db:
        db.execute("INSERT INTO judge_jobs VALUES(?,?,?,?,?,?,?,?)", ("judge_old", "visitor", "ip", "request", "payment", "RUNNING", 1, json.dumps(value)))
    directory = tmp_path / "runs" / "judge_old"
    directory.mkdir(parents=True)
    (directory / "progress.json").write_text(json.dumps({"active_stage": "RELAY", "workflow": {
        "workflow_id": "original", "outcome": {"tx_hash": "0xknown", "status": "SUBMITTED_UNKNOWN"}}}))
    first.close()
    second = JudgeController(settings, runner=lambda *_: pytest.fail("Restart must not submit"))
    second.start()
    try:
        observed = second.get("visitor", id_="judge_old")
        assert observed["status"] == "INTERRUPTED"
        assert observed["workflow"]["outcome"]["tx_hash"] == "0xknown"
        assert observed["public_chain_broadcast"] is True
        assert observed["active_stage"] == "RELAY"
    finally:
        second.close()


def test_probe_worker_receives_no_signing_keys_or_model_secrets(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from treasury_backend.modules.workflows import judge

    settings = JudgeSettings(data_dir=tmp_path, execution_mode="REAL_FUJI_EXECUTION", manifest_file=tmp_path/"manifest.json")
    controller = JudgeController(settings)
    with controller.db() as db:
        db.execute("INSERT INTO judge_jobs VALUES(?,?,?,?,?,?,?,?)", ("judge_probe", "visitor", "ip", "request", "swap", "RUNNING", 1, json.dumps({"attack": "swap-route"})))
    directory = tmp_path/"runs"/"judge_probe"
    directory.mkdir(parents=True)
    (directory/"result.json").write_text(json.dumps({"environment": "REAL_FUJI_EXECUTION", "status": "REJECTED", "public_chain_broadcast": False}))
    monkeypatch.setattr(judge, "worker_environment", lambda _: {
        "PYTHONPATH": "source", "PACEVANT_JUDGE_RPC_URL": settings.rpc_url,
        "PACEVANT_MVP_MANIFEST_FILE": str(settings.manifest_file),
        "PACEVANT_JUDGE_EXECUTION_MODE": "REAL_FUJI_EXECUTION",
        "PACEVANT_ATTESTOR_KEY": "never-forward", "B_FUJI_RELAYER_PRIVATE_KEY": "never-forward",
        "DEEPSEEK_API_KEY": "never-forward"})
    captured = {}
    def spawn(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(wait=lambda **_: None)
    monkeypatch.setattr(judge.subprocess, "Popen", spawn)
    monkeypatch.setattr(judge, "stop_tree", lambda _: None)
    controller.run_worker("judge_probe", "swap")
    assert captured["command"][-2:] == ["--attack", "swap-route"]
    assert not any("KEY" in key or "TOKEN" in key for key in captured["env"])
    controller.close()
