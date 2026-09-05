"""API key plugin: issuance, verification, quotas and rate limiting.

Semantics follow better-auth's `apiKey` plugin:
- the plaintext key is returned once at creation; only its SHA-256 is stored;
- `remaining` is a consumable quota (NULL = unlimited) optionally refilled every `refill_interval`;
- `rate_limit_*` is a fixed window: `request_count` resets when `last_request` is older than the window.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.config import ApiKeySettings
from app.modules.auth.access_control import Permissions, check_api_key_permissions
from app.modules.auth.constants import AuthErrorCode
from app.modules.auth.models import ApiKey
from app.modules.auth.repository import ApiKeyRepository
from app.modules.auth.security import generate_api_key, sha256_base64url
from app.shared.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    RateLimitError,
    ResourceNotFoundError,
)

_UNSET: Any = object()


@dataclass(slots=True)
class ApiKeyVerification:
    valid: bool
    key: ApiKey | None
    error_code: AuthErrorCode | None
    error_message: str | None


class ApiKeyService:
    def __init__(self, repo: ApiKeyRepository, settings: ApiKeySettings):
        self._repo = repo
        self._settings = settings

    # --- validation --------------------------------------------------------------------

    def _validate_name(self, name: str | None) -> None:
        if name is None:
            return
        if not (
            self._settings.min_name_length
            <= len(name)
            <= self._settings.max_name_length
        ):
            raise BadRequestError(
                f"Name must be between {self._settings.min_name_length} and "
                f"{self._settings.max_name_length} characters",
                code=AuthErrorCode.INVALID_NAME_LENGTH,
            )

    def _validate_expires_in(self, expires_in: int | None) -> None:
        if expires_in is None:
            return
        if expires_in < self._settings.min_expires_in_seconds:
            raise BadRequestError(
                f"expires_in must be at least {self._settings.min_expires_in_seconds} seconds",
                code=AuthErrorCode.EXPIRES_IN_IS_TOO_SMALL,
            )
        if expires_in > self._settings.max_expires_in_seconds:
            raise BadRequestError(
                f"expires_in must be at most {self._settings.max_expires_in_seconds} seconds",
                code=AuthErrorCode.EXPIRES_IN_IS_TOO_LARGE,
            )

    @staticmethod
    def _validate_refill(
        refill_amount: int | None, refill_interval: int | None
    ) -> None:
        if (refill_amount is None) != (refill_interval is None):
            raise BadRequestError(
                "refill_amount and refill_interval must be provided together",
                code=AuthErrorCode.REFILL_AMOUNT_AND_INTERVAL_REQUIRED,
            )

    # --- CRUD --------------------------------------------------------------------------

    async def create(
        self,
        *,
        user_id: UUID,
        name: str | None,
        prefix: str | None,
        expires_in: int | None,
        remaining: int | None,
        refill_amount: int | None,
        refill_interval: int | None,
        rate_limit_enabled: bool | None,
        rate_limit_time_window: int | None,
        rate_limit_max: int | None,
        permissions: Permissions | None,
        metadata: dict[str, Any] | None,
        config_id: str = "default",
    ) -> tuple[ApiKey, str]:
        """Returns `(record, plaintext_key)`. The plaintext is never recoverable afterwards."""
        self._validate_name(name)
        self._validate_expires_in(expires_in)
        self._validate_refill(refill_amount, refill_interval)
        if remaining is not None and remaining < 0:
            raise BadRequestError(
                "remaining must be >= 0", code=AuthErrorCode.INVALID_REMAINING
            )
        if prefix is not None and not (1 <= len(prefix) <= 32):
            raise BadRequestError(
                "Prefix must be between 1 and 32 characters",
                code=AuthErrorCode.INVALID_PREFIX_LENGTH,
            )

        effective_prefix = prefix or self._settings.default_prefix
        plaintext = generate_api_key(
            self._settings.default_key_length, effective_prefix
        )
        effective_expires_in = (
            expires_in
            if expires_in is not None
            else self._settings.default_expires_in_seconds
        )
        now = datetime.now(UTC)

        record = await self._repo.create(
            config_id=config_id,
            name=name,
            prefix=effective_prefix,
            start=plaintext[: self._settings.starting_characters_length],
            key=sha256_base64url(plaintext),
            reference_id=user_id,
            enabled=True,
            remaining=remaining
            if refill_amount is None
            else (remaining or refill_amount),
            refill_amount=refill_amount,
            refill_interval=refill_interval,
            last_refill_at=now if refill_amount is not None else None,
            rate_limit_enabled=(
                rate_limit_enabled
                if rate_limit_enabled is not None
                else self._settings.rate_limit_enabled
            ),
            rate_limit_time_window=(
                rate_limit_time_window
                if rate_limit_time_window is not None
                else self._settings.rate_limit_time_window_ms
            ),
            rate_limit_max=(
                rate_limit_max
                if rate_limit_max is not None
                else self._settings.rate_limit_max
            ),
            request_count=0,
            expires_at=(
                now + timedelta(seconds=effective_expires_in)
                if effective_expires_in is not None
                else None
            ),
            permissions=json.dumps(permissions) if permissions is not None else None,
            metadata_=json.dumps(metadata) if metadata is not None else None,
        )
        return record, plaintext

    async def get_owned(self, key_id: UUID, user_id: UUID) -> ApiKey:
        record = await self._repo.get_for_user(key_id, user_id)
        if record is None:
            raise ResourceNotFoundError("ApiKey", str(key_id))
        return record

    async def list_owned(self, user_id: UUID) -> list[ApiKey]:
        return await self._repo.list_for_user(user_id)

    async def update_owned(
        self,
        key_id: UUID,
        user_id: UUID,
        *,
        name: str | None = _UNSET,
        enabled: bool | None = _UNSET,
        remaining: int | None = _UNSET,
        refill_amount: int | None = _UNSET,
        refill_interval: int | None = _UNSET,
        expires_in: int | None = _UNSET,
        rate_limit_enabled: bool | None = _UNSET,
        rate_limit_time_window: int | None = _UNSET,
        rate_limit_max: int | None = _UNSET,
        permissions: Permissions | None = _UNSET,
        metadata: dict[str, Any] | None = _UNSET,
    ) -> ApiKey:
        record = await self.get_owned(key_id, user_id)
        changes: dict[str, object] = {}

        if name is not _UNSET:
            self._validate_name(name)
            changes["name"] = name
        if enabled is not _UNSET and enabled is not None:
            changes["enabled"] = enabled
        if remaining is not _UNSET:
            if remaining is not None and remaining < 0:
                raise BadRequestError(
                    "remaining must be >= 0", code=AuthErrorCode.INVALID_REMAINING
                )
            changes["remaining"] = remaining
        if refill_amount is not _UNSET or refill_interval is not _UNSET:
            new_amount = (
                record.refill_amount if refill_amount is _UNSET else refill_amount
            )
            new_interval = (
                record.refill_interval if refill_interval is _UNSET else refill_interval
            )
            self._validate_refill(new_amount, new_interval)
            changes["refill_amount"] = new_amount
            changes["refill_interval"] = new_interval
        if expires_in is not _UNSET:
            self._validate_expires_in(expires_in)
            changes["expires_at"] = (
                datetime.now(UTC) + timedelta(seconds=expires_in)
                if expires_in
                else None
            )
        if rate_limit_enabled is not _UNSET and rate_limit_enabled is not None:
            changes["rate_limit_enabled"] = rate_limit_enabled
        if rate_limit_time_window is not _UNSET:
            changes["rate_limit_time_window"] = rate_limit_time_window
        if rate_limit_max is not _UNSET:
            changes["rate_limit_max"] = rate_limit_max
        if permissions is not _UNSET:
            changes["permissions"] = (
                json.dumps(permissions) if permissions is not None else None
            )
        if metadata is not _UNSET:
            changes["metadata_"] = (
                json.dumps(metadata) if metadata is not None else None
            )

        if not changes:
            raise BadRequestError(
                "No values to update", code=AuthErrorCode.NO_VALUES_TO_UPDATE
            )
        return await self._repo.update(record, **changes)

    async def delete_owned(self, key_id: UUID, user_id: UUID) -> None:
        record = await self.get_owned(key_id, user_id)
        await self._repo.delete(record)

    # --- verification ------------------------------------------------------------------

    async def verify(
        self, plaintext: str, *, required_permissions: Permissions | None = None
    ) -> ApiKeyVerification:
        """Validate a key and account for one request (quota + rate limit). Never raises for bad keys."""
        record = await self._repo.get_by_hash(
            sha256_base64url(plaintext), for_update=True
        )
        if record is None:
            return ApiKeyVerification(
                False, None, AuthErrorCode.KEY_NOT_FOUND, "Invalid API key"
            )

        now = datetime.now(UTC)
        if not record.enabled:
            return ApiKeyVerification(
                False, record, AuthErrorCode.KEY_DISABLED, "API key is disabled"
            )
        if record.expires_at is not None and record.expires_at <= now:
            # better-auth deletes expired keys on verification
            await self._repo.delete(record)
            return ApiKeyVerification(
                False, None, AuthErrorCode.KEY_EXPIRED, "API key has expired"
            )

        changes: dict[str, object] = {}

        # Refill quota
        if (
            record.refill_amount is not None
            and record.refill_interval is not None
            and record.remaining is not None
        ):
            last = record.last_refill_at or record.created_at
            if now - last >= timedelta(milliseconds=record.refill_interval):
                record.remaining = record.refill_amount
                changes["remaining"] = record.refill_amount
                changes["last_refill_at"] = now

        # Consume quota
        if record.remaining is not None:
            if record.remaining <= 0:
                return ApiKeyVerification(
                    False,
                    record,
                    AuthErrorCode.USAGE_EXCEEDED,
                    "API key usage exceeded",
                )
            changes["remaining"] = record.remaining - 1

        # Fixed-window rate limit
        if (
            record.rate_limit_enabled
            and record.rate_limit_time_window is not None
            and record.rate_limit_max is not None
        ):
            window = timedelta(milliseconds=record.rate_limit_time_window)
            if record.last_request is None or now - record.last_request >= window:
                changes["request_count"] = 1
            elif record.request_count >= record.rate_limit_max:
                retry_after = (
                    int(((record.last_request + window) - now).total_seconds()) + 1
                )
                return ApiKeyVerification(
                    False,
                    record,
                    AuthErrorCode.RATE_LIMITED,
                    f"Rate limit exceeded; retry in {max(retry_after, 1)} seconds",
                )
            else:
                changes["request_count"] = record.request_count + 1

        if required_permissions and not check_api_key_permissions(
            self.permissions_of(record), required_permissions
        ):
            return ApiKeyVerification(
                False,
                record,
                AuthErrorCode.KEY_MISSING_PERMISSIONS,
                "API key lacks permissions",
            )

        changes["last_request"] = now
        await self._repo.update(record, **changes)
        return ApiKeyVerification(True, record, None, None)

    async def verify_or_raise(self, plaintext: str) -> ApiKey:
        result = await self.verify(plaintext)
        if result.valid and result.key is not None:
            return result.key
        match result.error_code:
            case AuthErrorCode.RATE_LIMITED:
                assert result.key is not None
                window_ms = result.key.rate_limit_time_window or 0
                raise RateLimitError(
                    retry_after=_retry_after_seconds(result.key),
                    limit=result.key.rate_limit_max or 0,
                    window=f"{window_ms // 1000} seconds",
                    code=AuthErrorCode.RATE_LIMITED,
                )
            case AuthErrorCode.USAGE_EXCEEDED | AuthErrorCode.KEY_DISABLED:
                raise AuthorizationError(
                    result.error_message or "Forbidden", code=result.error_code
                )
            case _:
                raise AuthenticationError(
                    result.error_message or "Invalid API key",
                    code=result.error_code or AuthErrorCode.INVALID_API_KEY,
                    www_authenticate='ApiKey realm="api"',
                )

    @staticmethod
    def permissions_of(record: ApiKey) -> dict[str, list[str]] | None:
        return json.loads(record.permissions) if record.permissions else None

    @staticmethod
    def metadata_of(record: ApiKey) -> dict[str, Any] | None:
        return json.loads(record.metadata_) if record.metadata_ else None


def _retry_after_seconds(record: ApiKey) -> int:
    if record.last_request is None or record.rate_limit_time_window is None:
        return 1
    reset_at = record.last_request + timedelta(
        milliseconds=record.rate_limit_time_window
    )
    return max(int((reset_at - datetime.now(UTC)).total_seconds()) + 1, 1)
