from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List

from sqlalchemy import select, func, literal, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProductRef, ProductSynonym


@dataclass(frozen=True)
class ProductCandidate:
    product_id: uuid.UUID
    name: str
    score: float
    source: str  # "name" or "synonym"


class ProductRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search_top_candidates(self, query: str, limit: int = 10) -> List[ProductCandidate]:
        """
        Возвращает кандидатов из:
        1) products_ref.name (похожее совпадение)
        2) product_synonyms.synonym -> product_ref
        Сортировка по score (similarity), лимит общий.
        """
        q = query.strip()
        if not q:
            return []

        # По названию
        by_name = (
            select(
                ProductRef.id.label("product_id"),
                ProductRef.name.label("name"),
                func.similarity(ProductRef.name, q).label("score"),
                literal("name").label("source"),
            )
            .where(ProductRef.name.op("%")(q))
        )

        # По синонимам
        by_syn = (
            select(
                ProductRef.id.label("product_id"),
                ProductRef.name.label("name"),
                func.similarity(ProductSynonym.synonym, q).label("score"),
                literal("synonym").label("source"),
            )
            .select_from(ProductSynonym)
            .join(ProductRef, ProductRef.id == ProductSynonym.product_ref_id)
            .where(ProductSynonym.synonym.op("%")(q))
        )

        merged = union_all(by_name, by_syn).subquery()

        # Можно получить повторы (name и synonym на один и тот же продукт).
        # Берем максимум score по продукту.
        final_q = (
            select(
                merged.c.product_id,
                merged.c.name,
                func.max(merged.c.score).label("score"),
                func.max(merged.c.source).label("source"),
            )
            .group_by(merged.c.product_id, merged.c.name)
            .order_by(func.max(merged.c.score).desc(), merged.c.name.asc())
            .limit(limit)
        )

        rows = (await self.session.execute(final_q)).all()
        return [
            ProductCandidate(
                product_id=r.product_id,
                name=str(r.name),
                score=float(r.score or 0.0),
                source=str(r.source),
            )
            for r in rows
        ]

    async def get_product(self, product_id: uuid.UUID) -> ProductRef | None:
        q = select(ProductRef).where(ProductRef.id == product_id)
        return (await self.session.execute(q)).scalars().first()
