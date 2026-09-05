"""Single-use, purpose-scoped verification tokens.

The plaintext token only ever travels to the user; the DB stores an HMAC of it under a
purpose-prefixed `identifier`, so neither a DB leak nor a token from another flow can be replayed.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from app.modules.auth.repository import VerificationRepository
from app.modules.auth.security import generate_verification_token, hmac_sha256_hex


class VerificationPurpose(StrEnum):
    EMAIL_VERIFICATION = "email-verification"
    PASSWORD_RESET = "reset-password"
    CHANGE_EMAIL = "change-email"


class VerificationService:
    def __init__(self, repo: VerificationRepository, secret: str):
        self._repo = repo
        self._secret = secret

    def _identifier(self, purpose: VerificationPurpose, token: str) -> str:
        return f"{purpose}:{hmac_sha256_hex(self._secret, token)}"

    async def issue(
        self, purpose: VerificationPurpose, value: str, *, ttl_seconds: int
    ) -> str:
        """Persist `value` under a fresh token and return the plaintext token."""
        token = generate_verification_token()
        await self._repo.create(
            identifier=self._identifier(purpose, token),
            value=value,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        return token

    async def consume(self, purpose: VerificationPurpose, token: str) -> str | None:
        """Return the stored value and delete the record, or None if missing/expired."""
        identifier = self._identifier(purpose, token)
        record = await self._repo.get_by_identifier(identifier)
        if record is None:
            return None
        # Always burn the identifier, even if expired, so a stale token cannot be probed
        await self._repo.delete_by_identifier(identifier)
        if record.expires_at <= datetime.now(UTC):
            return None
        return record.value
