"""Session cookie management (mirrors better-auth `session` and `bearer` plugin)."""

from datetime import UTC, datetime

from fastapi import Response

from app.core.config import AuthSettings
from app.modules.auth.models import Session


def set_session_cookie(
    response: Response, settings: AuthSettings, session: Session
) -> None:
    cookie = settings.session
    response.set_cookie(
        key=cookie.cookie_name,
        value=session.token,
        max_age=max(int((session.expires_at - datetime.now(UTC)).total_seconds()), 0),
        httponly=True,
        secure=cookie.cookie_secure,
        samesite=cookie.cookie_same_site,
        domain=cookie.cookie_domain,
        path="/",
    )
    # Mirror better-auth `bearer` plugin so header-based clients can capture the token
    response.headers["set-auth-token"] = session.token


def clear_session_cookie(response: Response, settings: AuthSettings) -> None:
    cookie = settings.session
    response.delete_cookie(
        key=cookie.cookie_name,
        httponly=True,
        secure=cookie.cookie_secure,
        samesite=cookie.cookie_same_site,
        domain=cookie.cookie_domain,
        path="/",
    )
