"""Generic async repository pattern for SQLAlchemy 2.0."""

from typing import Literal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.base import Base


class AsyncRepository[T: Base]:
    """Generic async repository for CRUD operations."""

    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model

    async def get(self, entity_id: UUID) -> T | None:
        """Get entity by ID."""
        return await self.session.get(self.model, entity_id)

    async def get_by_ids(self, ids: list[UUID]) -> list[T]:
        """Get multiple entities by IDs."""
        if not ids:
            return []
        result = await self.session.execute(
            select(self.model).where(self.model.id.in_(ids))
        )
        return list(result.scalars().all())

    async def list_page(
        self,
        *,
        cursor: UUID | None = None,
        limit: int = 100,
        direction: Literal["asc", "desc"] = "desc",
    ) -> tuple[list[T], UUID | None]:
        """Keyset-paginate by id; returns items and the next page's cursor."""
        stmt = select(self.model)
        if cursor is not None:
            stmt = stmt.where(
                self.model.id > cursor if direction == "asc" else self.model.id < cursor
            )
        stmt = stmt.order_by(
            self.model.id.asc() if direction == "asc" else self.model.id.desc()
        ).limit(limit + 1)

        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        next_cursor: UUID | None = None
        if len(items) > limit >= 1:
            # Extra row is the probe for whether another page exists
            items = items[:limit]
            next_cursor = items[-1].id
        return items, next_cursor

    async def create(self, **kwargs: object) -> T:
        """Create new entity."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def create_many(self, items: list[dict[str, object]]) -> list[T]:
        """Create multiple entities."""
        instances = [self.model(**item) for item in items]
        self.session.add_all(instances)
        await self.session.flush()
        return instances

    async def update(self, instance: T, **kwargs: object) -> T:
        """Update entity attributes."""
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: T) -> None:
        """Hard delete entity."""
        await self.session.delete(instance)
        await self.session.flush()

    async def delete_by_id(self, entity_id: UUID) -> None:
        await self.session.execute(delete(self.model).where(self.model.id == entity_id))
        await self.session.flush()

    async def exists(self, entity_id: UUID) -> bool:
        """Check if entity exists."""
        result = await self.session.execute(
            select(self.model.id).where(self.model.id == entity_id)
        )
        return result.scalar_one_or_none() is not None

    async def count(self) -> int:
        """Count all entities."""
        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar_one()
