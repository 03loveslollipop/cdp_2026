import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import joblib
import jwt
import numpy as np
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from mlops_pipeline.src.deployment.database.passwords import hash_password
from mlops_pipeline.src.deployment.model_auth.app import create_app as create_auth_app
from mlops_pipeline.src.deployment.model_auth.services.auth_service import AuthService
from mlops_pipeline.src.deployment.model_auth.settings import AuthSettings
from mlops_pipeline.src.deployment.model_deploy.api.model import model_metadata
from mlops_pipeline.src.deployment.model_deploy.app import create_app
from mlops_pipeline.src.deployment.model_deploy.models import LoadedArtifact
from mlops_pipeline.src.deployment.model_deploy.services import artifact_loader
from mlops_pipeline.src.deployment.service_clients.contracts import (
    AuthRole,
    AuthenticationError,
    SERVICE_TOKEN_HEADER,
    TOKEN_TTL_SECONDS,
)
from mlops_pipeline.src.deployment.model_deploy.services.prediction_service import (
    IdempotencyConflictError,
    PredictionService,
    PredictionValidationError,
)
from mlops_pipeline.src.deployment.model_deploy.settings import Settings
from mlops_pipeline.src.deployment.model_monitoring.visualization.app import (
    create_app as create_monitoring_app,
)
from mlops_pipeline.src.deployment.model_monitoring.visualization.settings import (
    VisualizationSettings,
)
from mlops_pipeline.src.deployment.install_model_runtime import FAMILY_REQUIREMENTS


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
        self.last_values = None

    def by_idempotency_key(self, key, requested_by_user_id):
        return self.saved.get((requested_by_user_id, key))

    def save_completed(self, **values):
        self.last_values = values
        batch = SimpleNamespace(
            id="batch-1",
            request_sha256=values["request_sha256"],
            model_version_id=values["model_version_id"],
            model_family="random_forest",
        )
        events = [
            SimpleNamespace(
                id=f"event-{index}",
                row_number=index,
                external_reference=reference,
                predicted_label=prediction,
                default_probability=probability[0],
                on_time_probability=probability[1],
            )
            for index, (reference, prediction, probability) in enumerate(
                zip(
                    values["external_references"],
                    values["predictions"],
                    values["probabilities"],
                    strict=True,
                )
            )
        ]
        self.saved[
            (values["requested_by_user_id"], values["idempotency_key"])
        ] = (batch, events)
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


class FakeAuthSessionFactory:
    def __init__(self):
        self.users = {
            "inference-id": SimpleNamespace(
                id="inference-id",
                username="inference-user",
                password_hash=hash_password("inference-secret"),
                role="inference",
                active=True,
                token_version=0,
                last_login_at=None,
            ),
            "owner-id": SimpleNamespace(
                id="owner-id",
                username="owner-user",
                password_hash=hash_password("owner-secret"),
                role="owner",
                active=True,
                token_version=0,
                last_login_at=None,
            ),
        }

    def __call__(self):
        return FakeAuthSessionContext(self.users)

    def begin(self):
        return FakeAuthSessionContext(self.users)


class FakeAuthSessionContext:
    def __init__(self, users):
        self.session = SimpleNamespace(users=users)

    def __enter__(self):
        return self.session

    def __exit__(self, *_args):
        return False


class FakeAuthUserRepository:
    def __init__(self, session):
        self.users = session.users

    def active_owner_count(self):
        return sum(
            user.active and user.role == "owner" for user in self.users.values()
        )

    def by_id(self, user_id):
        return self.users.get(user_id)

    def by_username(self, username):
        return next(
            (user for user in self.users.values() if user.username == username), None
        )

    def record_login(self, user, password_hash=None):
        user.last_login_at = datetime.now(UTC)
        if password_hash is not None:
            user.password_hash = password_hash


class FakeRemoteAuthClient:
    def __init__(self, service):
        self.service = service

    async def login(self, username, password):
        grant = self.service.login(username, password)
        return {
            "access_token": grant.token,
            "token_type": "bearer",
            "expires_in": 7200,
            "expires_at": grant.principal.expires_at.isoformat(),
            "role": grant.principal.role.value,
        }

    async def authenticate(self, token):
        return self.service.authenticate_token(token)

    async def jwks(self):
        return self.service.jwks()

    async def ready(self):
        return True


def artifact(model_family="random_forest"):
    return LoadedArtifact(
        model=FakeModel(),
        manifest={
            "model_family": model_family,
            "artifact_sha256": "a" * 64,
            "required_predictors": ["a", "b"],
            "threshold": 0.25,
            "class_order": [0, 1],
            "stage": "test",
            "source_revision": None,
        },
        reference_profiles={
            "a": {"type": "numeric"},
            "b": {
                "type": "categorical",
                "proportions": {"first": 0.75, "second": 0.25},
            },
        },
    )


@pytest.fixture
def auth_settings():
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return AuthSettings(
        jwt_private_key=private_pem,
        jwt_public_key=public_pem,
        internal_service_token="service-token-which-is-long-enough-123",
        environment="development",
    )


@pytest.fixture
def inference_settings():
    return Settings(
        auth_service_url="https://auth.example.test",
        internal_service_token="service-token-which-is-long-enough-123",
        monitor_ui_url="https://monitor.example.test/",
        environment="development",
    )


@pytest.fixture
def auth_factory():
    return FakeAuthSessionFactory()


@pytest.fixture
def auth_service(monkeypatch, auth_settings, auth_factory):
    monkeypatch.setattr(
        "mlops_pipeline.src.deployment.model_auth.services.auth_service.AuthUserRepository",
        FakeAuthUserRepository,
    )
    return AuthService(auth_settings, auth_factory)


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
        "mlops_pipeline.src.deployment.model_deploy.services.prediction_service.PredictionRepository",
        lambda _session: repository,
    )
    service = PredictionService(
        artifact(),
        "model-1",
        FakeSessionFactory(),
        max_batch_rows=2,
        requested_by_user_id="inference-id",
    )
    records = [{"a": 1, "b": None, "_external_reference": "loan-1"}]
    first = service.predict(records, "request-123")
    second = service.predict(records, "request-123")
    assert not first["idempotent_replay"]
    assert second["idempotent_replay"]
    assert first["items"] == second["items"]
    assert first["items"][0]["default_probability"] == 0.4
    assert repository.last_values["requested_by_user_id"] == "inference-id"
    new_service = PredictionService(
        artifact("xgboost"),
        "model-2",
        FakeSessionFactory(),
        max_batch_rows=2,
        requested_by_user_id="inference-id",
    )
    cross_deployment_replay = new_service.predict(records, "request-123")
    assert cross_deployment_replay["model_version_id"] == "model-1"
    assert cross_deployment_replay["model_family"] == "random_forest"
    other_user_service = PredictionService(
        artifact("xgboost"),
        "model-2",
        FakeSessionFactory(),
        max_batch_rows=2,
        requested_by_user_id="owner-id",
    )
    other_user_result = other_user_service.predict(records, "request-123")
    assert not other_user_result["idempotent_replay"]
    assert other_user_result["model_version_id"] == "model-2"
    with pytest.raises(IdempotencyConflictError):
        service.predict([{"a": 2, "b": None}], "request-123")
    with pytest.raises(PredictionValidationError, match="schema mismatch"):
        service.predict([{"a": 1}], "request-456")
    with pytest.raises(PredictionValidationError, match="JSON scalar"):
        service.predict([{"a": {"nested": 1}, "b": None}], "request-789")
    assert len(repository.saved) == 2


def test_model_contract_drives_generic_visual_fields():
    runtime = SimpleNamespace(artifact=artifact(), model_version_id="model-1")
    response = model_metadata(runtime)
    assert response["required_predictors"] == ["a", "b"]
    assert response["predictor_fields"] == [
        {"name": "a", "data_type": "numeric", "suggested_values": []},
        {
            "name": "b",
            "data_type": "categorical",
            "suggested_values": ["first", "second"],
        },
    ]


def test_asymmetric_tokens_have_fixed_ttl_role_and_public_verification(
    auth_settings, auth_factory, auth_service
):
    grant = auth_service.login("INFERENCE-user", "inference-secret")
    principal = auth_service.authenticate_token(grant.token)
    assert principal.role is AuthRole.INFERENCE
    assert principal.username == "inference-user"
    assert principal.user_id == "inference-id"
    claims = jwt.decode(
        grant.token,
        auth_settings.jwt_public_key,
        algorithms=["EdDSA"],
        audience=auth_settings.jwt_audience,
        issuer=auth_settings.jwt_issuer,
    )
    assert claims["exp"] - claims["iat"] == TOKEN_TTL_SECONDS
    assert claims["role"] == "inference"
    assert claims["sub"] == "inference-id"
    assert claims["ver"] == 0
    assert datetime.fromtimestamp(claims["exp"], tz=UTC) == principal.expires_at
    jwk = auth_service.jwks()["keys"][0]
    assert jwk["kty"] == "OKP"
    assert jwk["crv"] == "Ed25519"
    with pytest.raises(AuthenticationError):
        auth_service.login("inference-user", "wrong")
    with pytest.raises(AuthenticationError):
        auth_service.authenticate_token(grant.token + "altered")
    auth_factory.users["inference-id"].token_version += 1
    with pytest.raises(AuthenticationError):
        auth_service.authenticate_token(grant.token)


def test_auth_service_login_introspection_and_discovery(auth_settings, auth_service):
    app = create_auth_app(auth_settings)
    app.state.auth_service = auth_service
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/.well-known/jwks.json").status_code == 200
    invalid = client.post(
        "/v1/auth/login",
        json={"username": "inference-user", "password": "wrong"},
    )
    assert invalid.status_code == 401
    inference_login = client.post(
        "/v1/auth/login",
        json={"username": "inference-user", "password": "inference-secret"},
    )
    assert inference_login.status_code == 200
    assert inference_login.json()["expires_in"] == 7200
    assert inference_login.json()["role"] == "inference"
    inference_token = inference_login.json()["access_token"]
    introspection_headers = {
        "Authorization": f"Bearer {inference_token}",
        SERVICE_TOKEN_HEADER: auth_settings.internal_service_token,
    }
    introspection = client.post(
        "/v1/auth/introspect", headers=introspection_headers
    )
    assert introspection.status_code == 200
    assert introspection.json()["user_id"] == "inference-id"
    assert introspection.json()["role"] == "inference"
    denied = dict(introspection_headers)
    denied[SERVICE_TOKEN_HEADER] = "incorrect-service-credential-123456"
    assert client.post("/v1/auth/introspect", headers=denied).status_code == 403


def test_inference_service_uses_remote_auth_and_has_no_monitoring_routes(
    inference_settings, auth_service
):
    app = create_app(inference_settings)
    app.state.runtime = SimpleNamespace(
        settings=inference_settings,
        artifact=artifact(),
        model_version_id="model-1",
        auth_client=FakeRemoteAuthClient(auth_service),
    )
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    home = client.get("/")
    assert home.status_code == 200
    assert '<label for="file">CSV file</label>' in home.text
    assert '<th scope="col">Result</th>' in home.text
    assert client.get("/inference/").status_code == 200
    assert client.get("/static/auth.js").status_code == 200
    assert client.get("/.well-known/jwks.json").status_code == 200
    assert client.get("/v1/model").status_code == 401
    assert (
        client.get("/v1/model", auth=("owner-user", "owner-secret")).status_code == 401
    )

    inference_login = client.post(
        "/v1/auth/login",
        json={"username": "inference-user", "password": "inference-secret"},
    )
    assert inference_login.status_code == 200
    inference_token = inference_login.json()["access_token"]
    inference_headers = {"Authorization": f"Bearer {inference_token}"}
    assert client.get("/v1/model", headers=inference_headers).status_code == 200
    assert client.post("/v1/outcomes", headers=inference_headers).status_code == 404
    assert client.get("/monitor/", headers=inference_headers).status_code == 404
    openapi = client.get("/openapi.json", headers=inference_headers).json()
    assert openapi["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    assert openapi["paths"]["/v1/predictions"]["post"]["security"] == [
        {"BearerAuth": []}
    ]

    owner_login = client.post(
        "/v1/auth/login",
        json={"username": "owner-user", "password": "owner-secret"},
    )
    assert owner_login.status_code == 200
    assert owner_login.json()["role"] == "owner"
    owner_token = owner_login.json()["access_token"]
    assert client.get("/v1/model").status_code == 401
    assert (
        client.get(
            "/v1/model", headers={"Authorization": f"Bearer {owner_token}"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/v1/auth/logout", headers={"Authorization": f"Bearer {owner_token}"}
        ).status_code
        == 204
    )
    assert "https://monitor.example.test/" in client.get("/").text


def test_monitoring_visualization_is_independent_and_owner_only(auth_service):
    settings = VisualizationSettings(
        auth_service_url="https://auth.example.test",
        internal_service_token="service-token-which-is-long-enough-123",
        inference_service_url="https://inference.example.test/",
        environment="development",
    )
    app = create_monitoring_app(settings)
    app.state.runtime = SimpleNamespace(
        settings=settings,
        auth_client=FakeRemoteAuthClient(auth_service),
        session_factory=FakeSessionFactory(),
    )
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/").status_code == 200

    inference_login = client.post(
        "/v1/auth/login",
        json={"username": "inference-user", "password": "inference-secret"},
    )
    inference_token = inference_login.json()["access_token"]
    assert (
        client.get(
            "/monitor/",
            headers={"Authorization": f"Bearer {inference_token}"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/outcomes",
            headers={"Authorization": f"Bearer {inference_token}"},
            json={"outcomes": []},
        ).status_code
        == 403
    )

    owner_login = client.post(
        "/v1/auth/login",
        json={"username": "owner-user", "password": "owner-secret"},
    )
    owner_token = owner_login.json()["access_token"]
    assert (
        client.get(
            "/monitor/", headers={"Authorization": f"Bearer {owner_token}"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/v1/outcomes",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"outcomes": []},
        ).status_code
        == 422
    )


def test_every_trainable_family_has_a_runtime_strategy():
    assert set(FAMILY_REQUIREMENTS) == {
        "logistic_regression",
        "decision_tree",
        "gaussian_nb",
        "random_forest",
        "extra_trees",
        "svm",
        "xgboost",
        "lightgbm",
        "pytorch_mlp",
    }


def test_pytorch_runtime_uses_the_cpu_package_index(monkeypatch, tmp_path):
    config = tmp_path / "deployment.json"
    config.write_text(json.dumps({"model_family": "pytorch_mlp"}))
    commands = []
    monkeypatch.setattr("sys.argv", ["install_model_runtime.py", str(config)])
    monkeypatch.setattr(
        "subprocess.run", lambda command, check: commands.append(command)
    )
    from mlops_pipeline.src.deployment import install_model_runtime

    install_model_runtime.main()
    assert "--index-url" in commands[0]
    assert "--extra-index-url" not in commands[0]
    assert "https://download.pytorch.org/whl/cpu" in commands[0]
