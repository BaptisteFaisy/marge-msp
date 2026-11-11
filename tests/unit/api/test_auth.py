"""Authentication and role resolution (spec 6, 17).

Dev mode trusts X-Actor-Id / X-Actor-Role (EF-ADM-03 demo identities).
Cognito mode verifies an HS256 signature with the configured keys and refuses
explicitly when no key is available — never a fake verification.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from tests.fakes.fake_store import FakeStore

from marge.api import AuthMode, CognitoConfig, create_app
from marge.api.auth import Actor, ActorRole, AuthError, resolve_actor

SECRET = "demo-secret"
KEY_ID = "k1"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def make_token(claims: dict, secret: str = SECRET, alg: str = "HS256") -> str:
    header = _b64url(json.dumps({"alg": alg, "kid": KEY_ID}).encode())
    payload = _b64url(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    digest = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(digest)}"


def valid_claims(**overrides) -> dict:
    claims = {
        "sub": "controller-01",
        "custom:role": "CONTROLLER",
        "aud": "marge-portal",
        "exp": int(time.time()) + 3600,
    }
    claims.update(overrides)
    return claims


CONFIG = CognitoConfig(client_id="marge-portal", jwks={KEY_ID: SECRET})


def cognito_app(**config_kwargs) -> TestClient:
    config = CognitoConfig(**config_kwargs) if config_kwargs else CONFIG
    return TestClient(create_app(FakeStore(), auth_mode=AuthMode.COGNITO, cognito_config=config))


def test_dev_mode_headers_resolve_actor(hdr) -> None:
    actor = resolve_actor(AuthMode.DEV, hdr("ACCOUNT_MANAGER", "am-01"))
    assert actor == Actor(actor_id="am-01", role=ActorRole.ACCOUNT_MANAGER)


def test_dev_mode_missing_headers_returns_401(client: TestClient) -> None:
    response = client.get("/v1/matches")
    assert response.status_code == 401


def test_dev_mode_unknown_role_returns_400(client: TestClient, hdr) -> None:
    response = client.get("/v1/matches", headers=hdr("SUPERUSER"))
    assert response.status_code == 400


def test_dev_mode_unknown_role_raises_auth_error(hdr) -> None:
    with pytest.raises(AuthError) as info:
        resolve_actor(AuthMode.DEV, hdr("NOT_A_ROLE"))
    assert info.value.status_code == 400


def test_cognito_without_keys_refuses_explicitly() -> None:
    app = cognito_app(client_id="marge-portal")  # no jwks -> cannot verify
    token = make_token(valid_claims())
    response = app.get("/v1/matches", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "not configured" in response.json()["detail"]


def test_cognito_valid_token_accepted() -> None:
    app = cognito_app()
    token = make_token(valid_claims())
    response = app.get("/v1/matches", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_cognito_bad_signature_rejected() -> None:
    app = cognito_app()
    token = make_token(valid_claims(), secret="wrong-secret")
    response = app.get("/v1/matches", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "signature" in response.json()["detail"]


def test_cognito_expired_token_rejected() -> None:
    app = cognito_app()
    token = make_token(valid_claims(exp=int(time.time()) - 3600))
    response = app.get("/v1/matches", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


def test_cognito_wrong_audience_rejected() -> None:
    app = cognito_app()
    token = make_token(valid_claims(aud="another-app"))
    response = app.get("/v1/matches", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_cognito_token_without_role_defaults_to_account_manager() -> None:
    claims = valid_claims()
    del claims["custom:role"]
    actor_token = make_token(claims)
    headers = {"Authorization": f"Bearer {actor_token}"}
    actor = resolve_actor(AuthMode.COGNITO, headers, config=CONFIG)
    assert actor.role == ActorRole.ACCOUNT_MANAGER
    assert actor.actor_id == "controller-01"


def test_cognito_missing_bearer_header_returns_401() -> None:
    app = cognito_app()
    response = app.get("/v1/matches")
    assert response.status_code == 401
