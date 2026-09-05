"""Outbound-email port.

better-auth delegates `sendVerificationEmail` / `sendResetPassword` / `sendChangeEmailVerification`
to user-supplied callbacks. `Mailer` is the equivalent seam; swap `LoggingMailer` for a real
provider in `lifespan`.
"""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class Mailer(Protocol):
    async def send_verification_email(
        self, *, to: str, url: str, token: str
    ) -> None: ...

    async def send_password_reset(self, *, to: str, url: str, token: str) -> None: ...

    async def send_change_email_verification(
        self, *, to: str, new_email: str, url: str, token: str
    ) -> None: ...


class LoggingMailer:
    """Development fallback: logs the link instead of sending it. Never use in production."""

    async def send_verification_email(self, *, to: str, url: str, token: str) -> None:
        logger.warning("verification_email", extra={"to": to, "url": url})

    async def send_password_reset(self, *, to: str, url: str, token: str) -> None:
        logger.warning("password_reset_email", extra={"to": to, "url": url})

    async def send_change_email_verification(
        self, *, to: str, new_email: str, url: str, token: str
    ) -> None:
        logger.warning(
            "change_email_verification",
            extra={"to": to, "new_email": new_email, "url": url},
        )
