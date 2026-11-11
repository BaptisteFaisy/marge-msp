"""RS256 Cognito verification with the standard library only (idea 61).

The RSA key below is a fixed 511-bit test key (not a secret, not reusable): it
is just big enough for PKCS#1 v1.5 with SHA-256, so the tests exercise the real
signature maths without installing ``cryptography`` on the CI workers.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time

import pytest

from marge.api.auth import AuthError, AuthMode, CognitoConfig, resolve_actor
from marge.api.cognito_jwks import CACHE, TokenError, fetch_jwks, verify_token

N = int(
    "724464d48179b00c35a3dbcf0b3bee6e4df13385eb0c956c24836b18d0af5938"
    "939247836d127e7e8b4e937e01824198f3b10a93145cd985bf7ed71c3c2f40a5",
    16,
)
D = int(
    "72102bc6a5685f80109b7cf3f476e2cf61268114114a026e6d147277d6f8f2c9"
    "d3202bddad448bf0b898debb3302df54e88e23f808a81e77994b6a46d6d0a981",
    16,
)
E = 65537
KID = "test-key-1"
ISSUER = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_testpool"
AUDIENCE = "4eq2vsdm0113eogsiaqetq9llc"
KEY_SIZE = 64
DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")

JWKS = {
    KID: {
        "kid": KID,
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "n": base64.urlsafe_b64encode(N.to_bytes(KEY_SIZE, "big")).decode().rstrip("="),
        "e": base64.urlsafe_b64encode(E.to_bytes(3, "big")).decode().rstrip("="),
    }
}


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _sign(signed: str) -> str:
    digest = hashlib.sha256(signed.encode("ascii")).digest()
    block = b"\x00\x01" + b"\xff" * (KEY_SIZE - len(DIGEST_INFO) - len(digest) - 3) + b"\x00"
    signature = pow(int.from_bytes(block + DIGEST_INFO + digest, "big"), D, N)
    return _b64url(signature.to_bytes(KEY_SIZE, "big"))


def make_token(
    claims: dict | None = None,
    *,
    header: dict | None = None,
    tamper_payload: bool = False,
) -> str:
    """Mint an RS256 token signed with the test key."""
    now = int(time.time())
    payload = {
        "sub": "controller-01",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "token_use": "id",
        "exp": now + 3600,
        "iat": now,
        "cognito:groups": ["CONTROLLER"],
    }
    payload.update(claims or {})
    head = {"alg": "RS256", "kid": KID, "typ": "JWT"}
    head.update(header or {})
    signed = f"{_b64url(json.dumps(head).encode())}.{_b64url(json.dumps(payload).encode())}"
    signature = _sign(signed)
    if tamper_payload:
        # Same signature, forged payload: exactly what a privilege-escalation
        # attempt looks like on the wire.
        head_part = signed.split(".")[0]
        forged = _b64url(json.dumps(dict(payload, **{"cognito:groups": ["EXECUTIVE"]})).encode())
        return f"{head_part}.{forged}.{signature}"
    return f"{signed}.{signature}"


@pytest.fixture(autouse=True)
def _clear_cache():
    CACHE.entries.clear()
    yield
    CACHE.entries.clear()


def test_a_valid_token_is_accepted() -> None:
    claims = verify_token(make_token(), issuer=ISSUER, audience=AUDIENCE, keys=JWKS)
    assert claims["sub"] == "controller-01"
    assert claims["cognito:groups"] == ["CONTROLLER"]


def test_a_tampered_payload_is_refused() -> None:
    """Changing a claim after signing must break the signature check."""
    with pytest.raises(TokenError, match="bad signature"):
        verify_token(make_token(tamper_payload=True), issuer=ISSUER, audience=AUDIENCE, keys=JWKS)


def test_hs256_is_refused() -> None:
    """Algorithm confusion: an HS256 header must never be accepted."""
    token = make_token(header={"alg": "HS256"})
    with pytest.raises(TokenError, match="unsupported algorithm"):
        verify_token(token, issuer=ISSUER, audience=AUDIENCE, keys=JWKS)


def test_alg_none_is_refused() -> None:
    token = make_token(header={"alg": "none"})
    with pytest.raises(TokenError):
        verify_token(token, issuer=ISSUER, audience=AUDIENCE, keys=JWKS)


def test_expired_token_is_refused() -> None:
    token = make_token({"exp": int(time.time()) - 10})
    with pytest.raises(TokenError, match="expired"):
        verify_token(token, issuer=ISSUER, audience=AUDIENCE, keys=JWKS)


def test_wrong_issuer_is_refused() -> None:
    token = make_token({"iss": "https://evil.example.com/pool"})
    with pytest.raises(TokenError, match="issuer"):
        verify_token(token, issuer=ISSUER, audience=AUDIENCE, keys=JWKS)


def test_wrong_audience_is_refused() -> None:
    token = make_token({"aud": "another-client"})
    with pytest.raises(TokenError, match="audience"):
        verify_token(token, issuer=ISSUER, audience=AUDIENCE, keys=JWKS)


def test_client_id_claim_is_accepted_as_audience() -> None:
    """Access tokens carry ``client_id`` instead of ``aud``."""
    token = make_token({"aud": "", "client_id": AUDIENCE, "token_use": "access"})
    claims = verify_token(token, issuer=ISSUER, audience=AUDIENCE, keys=JWKS)
    assert claims["token_use"] == "access"


def test_unknown_kid_is_refused() -> None:
    token = make_token(header={"kid": "rotated-away"})
    with pytest.raises(TokenError, match="unknown signing key"):
        verify_token(token, issuer=ISSUER, audience=AUDIENCE, keys=JWKS)


def test_malformed_token_is_refused() -> None:
    for token in ("", "abc", "a.b", "a.b.c.d", "!!!.###.%%%"):
        with pytest.raises(TokenError):
            verify_token(token, issuer=ISSUER, audience=AUDIENCE, keys=JWKS)


def test_jwks_is_fetched_and_cached(monkeypatch) -> None:
    calls: list[str] = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return json.dumps({"keys": list(JWKS.values())}).encode()

    def fake_urlopen(url, timeout=5.0):
        calls.append(url)
        return _Response()

    import marge.api.cognito_jwks as module

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    first = fetch_jwks(ISSUER)
    second = fetch_jwks(ISSUER)
    assert first == second == JWKS
    assert len(calls) == 1, "the JWKS must be fetched once and cached"
    assert calls[0].endswith("/.well-known/jwks.json")


def test_resolve_actor_maps_the_cognito_group_to_a_role() -> None:
    CACHE.put(ISSUER, JWKS)  # no network in the tests
    config = CognitoConfig(issuer=ISSUER, client_id=AUDIENCE, user_pool_id="eu-west-1_testpool")
    token = make_token({"sub": "am-01", "cognito:groups": ["ACCOUNT_MANAGER"]})
    actor = resolve_actor(AuthMode.COGNITO, {"Authorization": f"Bearer {token}"}, config=config)
    assert actor.actor_id == "am-01"
    assert actor.role.value == "ACCOUNT_MANAGER"


def test_resolve_actor_refuses_without_configuration() -> None:
    with pytest.raises(AuthError) as error:
        resolve_actor(AuthMode.COGNITO, {"Authorization": "Bearer x"}, config=CognitoConfig())
    assert error.value.status_code == 401


def test_resolve_actor_reports_an_unreachable_provider() -> None:
    """No silent downgrade to dev mode when the JWKS cannot be read."""
    import marge.api.cognito_jwks as module

    def boom(url, timeout=5.0):
        raise OSError("network down")

    original = module.urllib.request.urlopen
    module.urllib.request.urlopen = boom
    try:
        config = CognitoConfig(issuer=ISSUER, client_id=AUDIENCE)
        with pytest.raises(AuthError) as error:
            resolve_actor(AuthMode.COGNITO, {"Authorization": f"Bearer {make_token()}"}, config=config)
        assert error.value.status_code == 503
    finally:
        module.urllib.request.urlopen = original


def test_issuer_url_is_derived_from_the_pool_id() -> None:
    config = CognitoConfig(user_pool_id="eu-west-1_abc123", client_id=AUDIENCE)
    assert config.issuer_url == "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_abc123"
    assert config.can_verify is True


def test_an_empty_config_cannot_verify() -> None:
    assert CognitoConfig().can_verify is False
    assert CognitoConfig().issuer_url == ""
