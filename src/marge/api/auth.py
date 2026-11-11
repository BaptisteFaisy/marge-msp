"""Actor resolution from the request token (spec 6, 17).

Two modes, chosen at app construction:

* ``dev`` — the demo portal sends ``X-Actor-Id`` and ``X-Actor-Role`` headers
  (EF-ADM-03). Fast and offline; it is never the production path.
* ``cognito`` — the ``Authorization: Bearer <jwt>`` header is decoded. When JWKS
  keys are supplied the signature **must** verify; otherwise the request is
  refused with 401. There is no fake verification: a production deployment can
  never silently accept an unsigned token.

Roles come from ``marge.domain.ActorRole`` (spec 6). Nothing here computes a
number or imports boto3.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from ..domain import ActorRole

ACTOR_ID_HEADER = "X-Actor-Id"
ACTOR_ROLE_HEADER = "X-Actor-Role"


class AuthMode(StrEnum):
    """How the actor identity is resolved from the request."""

    DEV = "dev"
    COGNITO = "cognito"


@dataclass(frozen=True, slots=True)
class CognitoConfig:
    """Verification material for the Cognito mode.

    ``jwks`` maps a key id to its raw HMAC secret (demo/HS256) or public key.
    When it is empty, Cognito mode refuses every token instead of pretending to
    verify a signature it cannot check.
    """

    user_pool_id: str = ""
    client_id: str = ""
    jwks: Mapping[str, str] | None = None
    leeway_seconds: int = 60

    @property
    def can_verify(self) -> bool:
        return bool(self.jwks)


@dataclass(frozen=True, slots=True)
class Actor:
    """The authenticated caller: who they are and what they may do."""

    actor_id: str
    role: ActorRole

    @property
    def is_account_manager(self) -> bool:
        return self.role == ActorRole.ACCOUNT_MANAGER

    @property
    def sees_hourly_costs(self) -> bool:
        """ENF-CONF-03: hourly costs are for the controller and management."""
        return self.role in (
            ActorRole.CONTROLLER,
            ActorRole.EXECUTIVE,
            ActorRole.OPERATIONS_DIRECTOR,
            ActorRole.ADMINISTRATOR,
        )

    @property
    def manages_settings(self) -> bool:
        return self.role in (ActorRole.CONTROLLER, ActorRole.ADMINISTRATOR)

    @property
    def sees_all_clients(self) -> bool:
        return not self.is_account_manager


class AuthError(Exception):
    """Raised when the token cannot be trusted; carries an HTTP status."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _decode_segment(segment: str) -> dict:
    """Decode one base64url JWT segment into a dict."""
    padding = "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(segment + padding)
    except (binascii.Error, ValueError) as exc:
        raise AuthError(401, "malformed token segment") from exc
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuthError(401, "token segment is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise AuthError(401, "token segment is not an object")
    return decoded


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _expected_signature(signing_input: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), "sha256").digest()
    return _b64url_encode(digest)


def _verify_signature(token: str, config: CognitoConfig) -> None:
    """Verify the HS256 signature, or refuse when no key is available."""
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError(401, "token is not a JWS compact serialization")
    header = _decode_segment(parts[0])
    if header.get("alg") != "HS256":
        raise AuthError(401, f"unsupported signing algorithm: {header.get('alg')!r}")
    key_id = str(header.get("kid", ""))
    secret = (config.jwks or {}).get(key_id)
    if secret is None:
        # No fake verification: an unknown/missing key is an explicit refusal.
        raise AuthError(401, "token signature cannot be verified (unknown or absent key)")
    signing_input = f"{parts[0]}.{parts[1]}"
    if not hmac.compare_digest(_expected_signature(signing_input, secret), parts[2]):
        raise AuthError(401, "invalid token signature")


def _validate_claims(claims: dict, config: CognitoConfig) -> None:
    now = int(time.time())
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp + config.leeway_seconds < now:
        raise AuthError(401, "token has expired")
    aud = claims.get("aud") or claims.get("client_id")
    if config.client_id and aud != config.client_id:
        raise AuthError(401, "token audience does not match this deployment")


def _role_from_claims(claims: dict) -> ActorRole:
    """Read the role from Cognito custom claims, defaulting to the narrowest."""
    candidates = (
        claims.get("custom:role"),
        claims.get("role"),
        claims.get("cognito:role"),
    )
    for raw in candidates:
        if isinstance(raw, str):
            try:
                return ActorRole(raw.upper())
            except ValueError:
                continue
    # A token without a recognised role gets no privilege beyond its own rows.
    return ActorRole.ACCOUNT_MANAGER


def _actor_from_claims(claims: dict, config: CognitoConfig) -> Actor:
    _validate_claims(claims, config)
    actor_id = claims.get("sub") or claims.get("username") or claims.get("cognito:username")
    if not isinstance(actor_id, str) or not actor_id:
        raise AuthError(401, "token carries no subject")
    return Actor(actor_id=actor_id, role=_role_from_claims(claims))


def _actor_from_dev(headers: Mapping[str, str]) -> Actor:
    actor_id = headers.get(ACTOR_ID_HEADER, "")
    raw_role = headers.get(ACTOR_ROLE_HEADER, "")
    if not actor_id or not raw_role:
        raise AuthError(401, "dev mode requires X-Actor-Id and X-Actor-Role headers")
    try:
        role = ActorRole(raw_role.upper())
    except ValueError as exc:
        raise AuthError(400, f"unknown role: {raw_role!r}") from exc
    return Actor(actor_id=actor_id, role=role)


def resolve_actor(
    mode: AuthMode,
    headers: Mapping[str, str],
    *,
    config: CognitoConfig | None = None,
) -> Actor:
    """Resolve the caller from the request headers (spec 6, 17)."""
    if mode == AuthMode.DEV:
        return _actor_from_dev(headers)

    config = config or CognitoConfig()
    if not config.can_verify:
        # Refuse explicitly: never fall back to trusting an unverified token.
        raise AuthError(401, "cognito verification is not configured; refusing token")
    authorization = headers.get("Authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise AuthError(401, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthError(401, "empty bearer token")
    _verify_signature(token, config)
    claims = _decode_segment(token.split(".")[1])
    return _actor_from_claims(claims, config)
