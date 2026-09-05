"""User persistence."""

from typing import Literal
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
from app.shared.db.repository import AsyncRepository

type UserSortField = Literal["created_at", "updated_at", "email", "name", "role"]
type SearchField = Literal["email", "name"]
type SearchOperator = Literal["contains", "starts_with", "ends_with"]


class UserRepository(AsyncRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str, *, exclude_id: UUID | None = None) -> bool:
        stmt = select(User.id).where(User.email == email.lower())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def search(
        self,
        *,
        search_value: str | None = None,
        search_field: SearchField = "email",
        search_operator: SearchOperator = "contains",
        filter_field: Literal["role", "banned", "email_verified"] | None = None,
        filter_value: str | bool | None = None,
        sort_by: UserSortField = "created_at",
        sort_direction: Literal["asc", "desc"] = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """Offset-paginated admin listing (mirrors better-auth `list-users`).

        Returns `(users, total)` where `total` counts every row matching the filters.
        """
        conditions: list[ColumnElement[bool]] = []

        if search_value:
            column = User.email if search_field == "email" else User.name
            pattern = _escape_like(search_value)
            match search_operator:
                case "contains":
                    conditions.append(column.ilike(f"%{pattern}%", escape="\\"))
                case "starts_with":
                    conditions.append(column.ilike(f"{pattern}%", escape="\\"))
                case "ends_with":
                    conditions.append(column.ilike(f"%{pattern}", escape="\\"))

        if filter_field is not None and filter_value is not None:
            match filter_field:
                case "role":
                    conditions.append(User.role == str(filter_value))
                case "banned":
                    conditions.append(User.banned == _as_bool(filter_value))
                case "email_verified":
                    conditions.append(User.email_verified == _as_bool(filter_value))

        base = select(User).where(*conditions)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        sort_column = getattr(User, sort_by)
        order = sort_column.asc() if sort_direction == "asc" else sort_column.desc()
        # Secondary key on id keeps paging stable when sort_column has duplicates
        stmt = base.order_by(order, User.id.desc()).limit(limit).offset(offset)
        users = list((await self.session.execute(stmt)).scalars().all())
        return users, total


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes"}
