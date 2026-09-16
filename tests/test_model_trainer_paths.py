"""Build-time artifact and configuration paths remain inside the checkout."""

from __future__ import annotations

import pytest

from mlops_pipeline.src.deployment.model_deploy.services import model_trainer


def test_deployment_artifacts_cannot_escape_ignored_directory(monkeypatch, tmp_path):
    artifact_root = tmp_path / "deployment_artifacts"
    monkeypatch.setattr(model_trainer, "ARTIFACT_ROOT", artifact_root)

    assert model_trainer._artifact_path(artifact_root / "run") == artifact_root / "run"
    artifact_root.mkdir()
    model_trainer._json(artifact_root / "manifest.json", {"stage": "test"})
    assert (artifact_root / "manifest.json").read_text(encoding="utf-8").endswith(
        '"stage": "test"\n}\n'
    )
    with pytest.raises(ValueError, match="deployment_artifacts"):
        model_trainer.train_deployment_artifact(tmp_path / "outside")
    assert not (tmp_path / "outside").exists()

    outside = tmp_path / "outside"
    outside.mkdir()
    (artifact_root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="deployment_artifacts"):
        model_trainer._artifact_path(artifact_root / "link" / "model.joblib")


def test_deployment_config_must_be_a_checkout_file(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    inside = project_root / "deployment_model_config.json"
    inside.write_text("{}", encoding="utf-8")
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(model_trainer, "PROJECT_ROOT", project_root)

    assert model_trainer._project_file(inside) == inside
    with pytest.raises(ValueError, match="checkout"):
        model_trainer.load_deployment_config(outside)
