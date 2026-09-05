"""Role → permission mapping (better-auth admin plugin `createAccessControl`).

A *permission* is `{resource: [action, ...]}`. A role is granted if, for every requested
resource, every requested action is in the role's action set for that resource.
"""

from collections.abc import Mapping, Sequence
from uuid import UUID

from app.core.config import AdminSettings

type Permissions = Mapping[str, Sequence[str]]

# Mirrors better-auth `defaultStatements`
DEFAULT_STATEMENTS: dict[str, tuple[str, ...]] = {
    "user": (
        "create",
        "list",
        "set-role",
        "ban",
        "impersonate",
        "impersonate-admins",
        "delete",
        "set-password",
        "set-email",
        "get",
        "update",
    ),
    "session": ("list", "revoke", "delete"),
}

# Mirrors better-auth `defaultRoles`: admin gets every statement except `impersonate-admins`
# (granted via `allow_impersonating_admins` or a custom role), user gets none.
DEFAULT_ROLES: dict[str, dict[str, frozenset[str]]] = {
    "admin": {
        "user": frozenset(DEFAULT_STATEMENTS["user"]) - {"impersonate-admins"},
        "session": frozenset(DEFAULT_STATEMENTS["session"]),
    },
    "user": {},
}


class AccessControl:
    def __init__(
        self,
        settings: AdminSettings,
        roles: Mapping[str, Mapping[str, frozenset[str]]] = DEFAULT_ROLES,
    ):
        self._settings = settings
        self._roles = roles

    def roles_of(self, role: str | None) -> list[str]:
        raw = role or self._settings.default_role
        return [r.strip() for r in raw.split(",") if r.strip()]

    def is_admin(self, *, user_id: UUID, role: str | None) -> bool:
        if str(user_id) in self._settings.admin_user_ids:
            return True
        return any(r in self._settings.admin_roles for r in self.roles_of(role))

    def has_permission(
        self, *, user_id: UUID, role: str | None, permissions: Permissions
    ) -> bool:
        if not permissions:
            return False
        # `admin_user_ids` are unconditional admins (better-auth behaviour)
        if str(user_id) in self._settings.admin_user_ids:
            return True

        for candidate in self.roles_of(role):
            granted = self._roles.get(candidate)
            if granted is None:
                continue
            if all(
                set(actions) <= granted.get(resource, frozenset())
                for resource, actions in permissions.items()
            ):
                return True
        return False


def check_api_key_permissions(
    key_permissions: Permissions | None, required: Permissions
) -> bool:
    """API-key permissions are a flat allow-list stored on the key itself."""
    if not required:
        return True
    if not key_permissions:
        return False
    return all(
        set(actions) <= set(key_permissions.get(resource, ()))
        for resource, actions in required.items()
    )
