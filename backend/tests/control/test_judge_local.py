from treasury_backend.operations.judge_local import model_environment


def test_explicit_local_model_loader_never_imports_wallet_or_service_credentials(tmp_path):
    path = tmp_path / "source.env"
    path.write_text("DEEPSEEK_API_KEY=model-only\nPACEVANT_SHIELD_MODE=wallet_pipeline\n"
                    "B_FUJI_OWNER_PRIVATE_KEY=owner-secret\nPACEVANT_ATTESTOR_KEY=signer-secret\n"
                    "B_RELAYER_PRIVATE_KEY=relayer-secret\nB_API_KEY=service-secret\n"
                    "PACEVANT_MVP_LIVE_ENABLED=1\n", encoding="utf-8")
    assert model_environment(path) == {"DEEPSEEK_API_KEY": "model-only", "PACEVANT_SHIELD_MODE": "wallet_pipeline"}
