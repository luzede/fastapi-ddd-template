"""Request-scoped auth value objects shared by services, guards and routers."""

from dataclasses import dataclass

from app.modules.auth.models import Session, User


@dataclass(slots=True, frozen=True)
class ClientInfo:
    ip_address: str | None
    user_agent: str | None


@dataclass(slots=True)
class AuthContext:
    """The resolved principal for a request."""

    user: User
    session: Session
    via_api_key: bool = False
    """True when the principal was established from an API key (synthetic session, never persisted)."""

    @property
    def is_impersonation(self) -> bool:
        return self.session.impersonated_by is not None
