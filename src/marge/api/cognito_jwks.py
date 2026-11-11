"""Cognito JWT verification with the standard library only.

The Hosted UI issues RS256 tokens signed with the user pool's keys. Verifying
them normally pulls in ``cryptography`` or ``python-jose``; neither is available
on the CI workers, and a Lambda layer for one algorithm is not worth it. RSA
verification is a modular exponentiation, and a JWK publishes exactly what it
needs (``n`` and ``e`` in base64url), so the check is done here in ~80 lines:

1. split the compact JWT, check the header algorithm is RS256;
2. fetch and cache the pool's JWKS, pick the key by ``kid``;
3. verify the PKCS#1 v1.5 signature over ``header.payload``;
4. check ``iss``, ``aud`` (or ``client_id``), ``exp`` and ``token_use``.

Nothing here trusts a claim before the signature verifies: an unverifiable
token is refused, never downgraded (spec 17).
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

ALLOWED_ALGORITHMS = ("RS256",)
ALLOWED_TOKEN_USES = ("id", "access")
JWKS_CACHE_SECONDS = 300

# SHA-256 DigestInfo prefix, as required by PKCS#1 v1.5 (RFC 8017 §9.2).
_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


class TokenError(ValueError):
    """Any reason a token is refused. The message is safe to return to a client."""


@dataclass(slots=True)
class JwksCache:
    """In-process JWKS cache, one entry per issuer."""

    entries: dict[str, tuple[float, dict[str, dict[str, str]]]] = field(default_factory=dict)

    def get(self, issuer: str, max_age: float = JWKS_CACHE_SECONDS) -> dict[str, dict[str, str]] | None:
        cached = self.entries.get(issuer)
        if cached is None or (time.time() - cached[0]) > max_age:
            return None
        return cached[1]

    def put(self, issuer: str, keys: dict[str, dict[str, str]]) -> None:
        self.entries[issuer] = (time.time(), keys)


CACHE = JwksCache()


def _b64url_decode(segment: str) -> bytes:
    padded = segment + "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _b64url_to_int(segment: str) -> int:
    return int.from_bytes(_b64url_decode(segment), "big")


def fetch_jwks(issuer: str, timeout: float = 5.0) -> dict[str, dict[str, str]]:
    """Download and cache the JWKS of one issuer, keyed by ``kid``."""
    cached = CACHE.get(issuer)
    if cached is not None:
        return cached
    url = f"{issuer.rstrip('/')}/.well-known/jwks.json"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        document = json.loads(response.read().decode("utf-8"))
    keys = {key["kid"]: key for key in document.get("keys", []) if key.get("kid")}
    if not keys:
        raise TokenError("the identity provider published no key")
    CACHE.put(issuer, keys)
    return keys


def _pkcs1_verify(key: dict[str, str], signed: bytes, signature: bytes) -> bool:
    """PKCS#1 v1.5 verification with SHA-256, pure integers."""
    modulus = _b64url_to_int(key["n"])
    exponent = _b64url_to_int(key.get("e", "AQAB"))
    size = (modulus.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    recovered = pow(int.from_bytes(signature, "big"), exponent, modulus)
    block = recovered.to_bytes(size, "big")
    digest = hashlib.sha256(signed).digest()
    expected = _encode_pkcs1_block(_SHA256_DIGEST_INFO + digest, size)
    return _constant_time_equals(block, expected)


def _encode_pkcs1_block(digest_info: bytes, size: int) -> bytes:
    padding_length = size - len(digest_info) - 3
    if padding_length < 8:
        return b""
    return b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + digest_info


def _constant_time_equals(left: bytes, right: bytes) -> bool:
    if len(left) != len(right):
        return False
    difference = 0
    for a, b in zip(left, right, strict=True):
        difference |= a ^ b
    return difference == 0


def _split(token: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("malformed token")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        claims = json.loads(_b64url_decode(parts[1]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("malformed token") from exc
    signature = _b64url_decode(parts[2])
    signed = f"{parts[0]}.{parts[1]}".encode("ascii")
    return header, claims, signature, signed


def verify_token(
    token: str,
    *,
    issuer: str,
    audience: str,
    keys: dict[str, dict[str, str]] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Verify signature and claims; return the payload or raise ``TokenError``."""
    header, claims, signature, signed = _split(token)
    if header.get("alg") not in ALLOWED_ALGORITHMS:
        raise TokenError(f"unsupported algorithm: {header.get('alg')}")
    jwks = keys if keys is not None else fetch_jwks(issuer)
    key = jwks.get(header.get("kid", ""))
    if key is None:
        raise TokenError("unknown signing key")
    if not _pkcs1_verify(key, signed, signature):
        raise TokenError("bad signature")
    _check_claims(claims, issuer=issuer, audience=audience, now=now or time.time())
    return claims


def _check_claims(claims: dict[str, Any], *, issuer: str, audience: str, now: float) -> None:
    if claims.get("iss") != issuer:
        raise TokenError("unexpected issuer")
    if claims.get("token_use") not in ALLOWED_TOKEN_USES:
        raise TokenError("unexpected token_use")
    if audience not in (claims.get("aud"), claims.get("client_id")):
        raise TokenError("unexpected audience")
    expiry = claims.get("exp")
    if not isinstance(expiry, (int, float)) or expiry <= now:
        raise TokenError("token expired")
