"""JWT plugin: mint short-lived asymmetric tokens and publish the JWKS.

Behaviour mirrors better-auth's `jwt` plugin:
- keys are generated lazily on first use, stored encrypted, and published at `/jwks`;
- optional rotation: once the active key is older than `rotation_interval_seconds`, a new one is
  created and the old one gets `expires_at`, staying published for `grace_period_seconds`;
- payload is the user object plus `iat`, `exp`, `iss`, `aud`, `sub` (= user id).
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import AuthSettings
from app.modules.auth.constants import AuthErrorCode
from app.modules.auth.models import Jwks, User
from app.modules.auth.repository import JwksRepository
from app.modules.auth.security import (
    decrypt,
    encrypt,
    generate_key_pair,
    load_private_key,
    load_public_key,
)
from app.shared.exceptions import AuthenticationError, InternalError


class JwtService:
    def __init__(self, repo: JwksRepository, settings: AuthSettings):
        self._repo = repo
        self._settings = settings
        self._jwt = settings.jwt
        self._secret = settings.secret.get_secret_value()

    @property
    def issuer(self) -> str:
        return self._jwt.issuer or self._settings.base_url

    @property
    def audience(self) -> str | list[str]:
        return self._jwt.audience or self._settings.base_url

    async def _create_key(self) -> Jwks:
        private_jwk, public_jwk = generate_key_pair(
            self._jwt.algorithm,
            crv=self._jwt.curve,
            rsa_modulus_length=self._jwt.rsa_modulus_length,
        )
        return await self._repo.create(
            public_key=json.dumps(public_jwk),
            private_key=encrypt(self._secret, json.dumps(private_jwk)),
            alg=self._jwt.algorithm,
            crv=self._jwt.curve if self._jwt.algorithm == "EdDSA" else None,
        )

    async def get_signing_key(self) -> Jwks:
        """Latest non-retired key, rotating first if it is past the rotation interval."""
        key = await self._repo.get_latest_active()
        if key is None:
            return await self._create_key()

        rotation = self._jwt.rotation_interval_seconds
        if rotation is not None:
            age = datetime.now(UTC) - key.created_at
            if age >= timedelta(seconds=rotation):
                await self._repo.update(
                    key,
                    expires_at=datetime.now(UTC)
                    + timedelta(seconds=self._jwt.grace_period_seconds),
                )
                return await self._create_key()
        return key

    async def jwks(self) -> dict[str, list[dict[str, Any]]]:
        keys = await self._repo.list_all()
        if not keys:
            keys = [await self._create_key()]
        now = datetime.now(UTC)
        published: list[dict[str, Any]] = []
        for key in keys:
            # Retired keys stay published until their grace window closes
            if key.expires_at is not None and key.expires_at <= now:
                continue
            jwk = json.loads(key.public_key)
            published.append(
                {
                    "alg": key.alg or self._jwt.algorithm,
                    "use": "sig",
                    **jwk,
                    "kid": str(key.id),
                }
            )
        return {"keys": published}

    async def sign_for_user(
        self, user: User, *, claims: dict[str, Any] | None = None
    ) -> str:
        key = await self.get_signing_key()
        alg = key.alg or self._jwt.algorithm
        try:
            private_jwk = json.loads(decrypt(self._secret, key.private_key))
        except Exception as exc:  # wrong AUTH__SECRET or corrupted row
            raise InternalError("Signing key could not be decrypted") from exc

        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            # user object (better-auth default payload), excluding moderation fields
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "email_verified": user.email_verified,
            "image": user.image,
            "role": user.role,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat(),
            **(claims or {}),
            "iat": int(now.timestamp()),
            "exp": int(
                (now + timedelta(seconds=self._jwt.expiration_seconds)).timestamp()
            ),
            "iss": self.issuer,
            "aud": self.audience,
            "sub": str(user.id),
        }
        return jwt.encode(
            payload,
            load_private_key(alg, private_jwk),
            algorithm=alg,
            headers={"kid": str(key.id)},
        )

    async def verify(self, token: str) -> dict[str, Any]:
        """Verify a token minted by this service (for resource servers co-located with the issuer)."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthenticationError(
                "Invalid token", code=AuthErrorCode.INVALID_TOKEN
            ) from exc

        kid = header.get("kid")
        keys = await self._repo.list_all()
        now = datetime.now(UTC)
        candidate = next(
            (
                k
                for k in keys
                if str(k.id) == kid and (k.expires_at is None or k.expires_at > now)
            ),
            None,
        )
        if candidate is None:
            raise AuthenticationError(
                "Unknown signing key", code=AuthErrorCode.INVALID_TOKEN
            )

        alg = candidate.alg or self._jwt.algorithm
        try:
            return jwt.decode(
                token,
                load_public_key(alg, json.loads(candidate.public_key)),
                algorithms=[alg],
                issuer=self.issuer,
                audience=self.audience,
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(
                "Invalid token", code=AuthErrorCode.INVALID_TOKEN
            ) from exc
