import hashlib
import json
from types import SimpleNamespace

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient

from etl_scripts.src.model_deploy.app import create_app
from etl_scripts.src.model_deploy.models import LoadedArtifact
from etl_scripts.src.model_deploy.services import artifact_loader
from etl_scripts.src.model_deploy.services.prediction_service import (
    IdempotencyConflictError,
    PredictionService,
    PredictionValidationError,
)
from etl_scripts.src.model_deploy.settings import Settings
from scripts.install_model_runtime import FAMILY_REQUIREMENTS


class FakeModel:
    classes_ = np.array([0, 1])

    def predict_proba(self, frame):
        probability = np.repeat([[0.4, 0.6]], len(frame), axis=0)
        return probability

    def predict(self, frame):
        return np.ones(len(frame), dtype=int)


class FakePredictionRepository:
    def __init__(self):
        self.saved = {}

    def by_idempotency_key(self, key):
        return self.saved.get(key)

    def save_completed(self, **values):
        batch = SimpleNamespace(
            id="batch-1",
            request_sha256=values["request_sha256"],
        )
        events = [SimpleNamespace(
            id=f"event-{index}",
            row_number=index,
            external_reference=reference,
            predicted_label=prediction,
            default_probability=probability[0],
            on_time_probability=probability[1],
        ) for index, (reference, prediction, probability) in enumerate(zip(
            values["external_references"],
            values["predictions"],
            values["probabilities"],
            strict=True,
        ))]
        self.saved[values["idempotency_key"]] = (batch, events)
        return batch, events


class FakeSessionContext:
    def __enter__(self):
        return object()

    def __exit__(self, *_args):
        return False


class FakeSessionFactory:
    def __call__(self):
        return FakeSessionContext()

    def begin(self):
        return FakeSessionContext()


def artifact():
    return LoadedArtifact(
        model=FakeModel(),
        manifest={
            "model_family": "random_forest",
            "artifact_sha256": "a" * 64,
            "required_predictors": ["a", "b"],
        },
        reference_profiles={},
    )


def test_artifact_loader_verifies_hash_and_class_contract(tmp_path):
    model_path = tmp_path / artifact_loader.MODEL_FILE
    joblib.dump(FakeModel(), model_path)
    manifest = {
        "artifact_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "class_order": [0, 1],
        "model_family": "random_forest",
    }
    (tmp_path / artifact_loader.MANIFEST_FILE).write_text(json.dumps(manifest))
    (tmp_path / artifact_loader.PROFILES_FILE).write_text("{}")
    loaded = artifact_loader.load_artifact(tmp_path)
    assert loaded.model_family == "random_forest"
    manifest["artifact_sha256"] = "0" * 64
    (tmp_path / artifact_loader.MANIFEST_FILE).write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="SHA-256"):
        artifact_loader.load_artifact(tmp_path)


def test_prediction_service_is_atomic_and_idempotent(monkeypatch):
    repository = FakePredictionRepository()
    monkeypatch.setattr(
        "etl_scripts.src.model_deploy.services.prediction_service.PredictionRepository",
        lambda _session: repository,
    )
    service = PredictionService(
        artifact(), "model-1", FakeSessionFactory(), max_batch_rows=2
    )
    records = [{"a": 1, "b": None, "_external_reference": "loan-1"}]
    first = service.predict(records, "request-123")
    second = service.predict(records, "request-123")
    assert not first["idempotent_replay"]
    assert second["idempotent_replay"]
    assert first["items"] == second["items"]
    assert first["items"][0]["default_probability"] == 0.4
    with pytest.raises(IdempotencyConflictError):
        service.predict([{"a": 2, "b": None}], "request-123")
    with pytest.raises(PredictionValidationError, match="schema mismatch"):
        service.predict([{"a": 1}], "request-456")
    with pytest.raises(PredictionValidationError, match="JSON scalar"):
        service.predict([{"a": {"nested": 1}, "b": None}], "request-789")
    assert len(repository.saved) == 1


def test_app_authentication_frontend_and_dash_routes_smoke():
    app = create_app(Settings(auth_username="user", auth_password="secret"))
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("user", "secret")).status_code == 200
    assert client.get("/monitor/", auth=("user", "secret")).status_code == 200


def test_every_trainable_family_has_a_runtime_strategy():
    assert set(FAMILY_REQUIREMENTS) == {
        "logistic_regression", "decision_tree", "gaussian_nb", "random_forest",
        "extra_trees", "svm", "xgboost", "lightgbm", "pytorch_mlp",
    }


def test_pytorch_runtime_uses_the_cpu_package_index(monkeypatch, tmp_path):
    config = tmp_path / "deployment.json"
    config.write_text(json.dumps({"model_family": "pytorch_mlp"}))
    commands = []
    monkeypatch.setattr("sys.argv", ["install_model_runtime.py", str(config)])
    monkeypatch.setattr("subprocess.run", lambda command, check: commands.append(command))
    from scripts import install_model_runtime

    install_model_runtime.main()
    assert "--index-url" in commands[0]
    assert "--extra-index-url" not in commands[0]
    assert "https://download.pytorch.org/whl/cpu" in commands[0]
