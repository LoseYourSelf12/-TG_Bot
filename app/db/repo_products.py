from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional, Sequence

from sqlalchemy import select, func, literal, union_all, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProductRef, ProductSynonym


@dataclass(frozen=True)
class ProductCandidate:
    product_id: uuid.UUID
    name: str
    score: float
    source: str  # "name" or "synonym"


@dataclass(frozen=True)
class ProductWithSynonyms:
    product: ProductRef
    synonyms: list[str]

@dataclass(frozen=True)
class RankedCandidate:
    product_id: uuid.UUID
    name: str
    score: float
    bucket: int     # 0 exact, 1 name, 2 synonym

class ProductRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- used in meal mapping ---
    async def search_top_candidates(self, query: str, limit: int = 10) -> List[ProductCandidate]:
        q = query.strip()
        if not q:
            return []

        by_name = (
            select(
                ProductRef.id.label("product_id"),
                ProductRef.name.label("name"),
                func.similarity(ProductRef.name, q).label("score"),
                literal("name").label("source"),
            )
            .where(ProductRef.name.op("%")(q))
        )

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
    
    async def search_ranked_candidates(
        self,
        query: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[RankedCandidate], int]:
        """
        Возвращает кандидатов в порядке:
        bucket 0: точное совпадение products_ref.name == query
        bucket 1: частичное совпадение по названию (trgm)
        bucket 2: частичное совпадение по синонимам (trgm)

        Уникальность по product_id (если совпал и по name и по synonym — берём bucket=min, score=max).
        """
        q = (query or "").strip()
        if not q:
            return [], 0

        exact = select(
            ProductRef.id.label("product_id"),
            ProductRef.name.label("name"),
            literal(1.0).label("score"),
            literal(0).label("bucket"),
        ).where(ProductRef.name == q)

        by_name = select(
            ProductRef.id.label("product_id"),
            ProductRef.name.label("name"),
            func.similarity(ProductRef.name, q).label("score"),
            literal(1).label("bucket"),
        ).where(
            ProductRef.name.op("%")(q)
        ).where(
            ProductRef.name != q
        )

        by_syn = select(
            ProductRef.id.label("product_id"),
            ProductRef.name.label("name"),
            func.similarity(ProductSynonym.synonym, q).label("score"),
            literal(2).label("bucket"),
        ).select_from(ProductSynonym).join(
            ProductRef, ProductRef.id == ProductSynonym.product_ref_id
        ).where(
            ProductSynonym.synonym.op("%")(q)
        )

        merged = union_all(exact, by_name, by_syn).subquery()

        # Схлопываем дубли по product_id:
        # bucket = min(bucket), score = max(score)
        grouped = (
            select(
                merged.c.product_id,
                merged.c.name,
                func.max(merged.c.score).label("score"),
                func.min(merged.c.bucket).label("bucket"),
            )
            .group_by(merged.c.product_id, merged.c.name)
            .subquery()
        )

        total_q = select(func.count()).select_from(grouped)
        total = int((await self.session.execute(total_q)).scalar_one())

        page_q = (
            select(grouped.c.product_id, grouped.c.name, grouped.c.score, grouped.c.bucket)
            .order_by(
                grouped.c.bucket.asc(),
                grouped.c.score.desc(),
                grouped.c.name.asc(),
            )
            .offset(offset)
            .limit(limit)
        )

        rows = (await self.session.execute(page_q)).all()
        return (
            [
                RankedCandidate(
                    product_id=r.product_id,
                    name=str(r.name),
                    score=float(r.score or 0.0),
                    bucket=int(r.bucket),
                )
                for r in rows
            ],
            total,
        )

    async def get_product(self, product_id: uuid.UUID) -> ProductRef | None:
        q = select(ProductRef).where(ProductRef.id == product_id)
        return (await self.session.execute(q)).scalars().first()

    # --- admin / reference management ---
    async def count_ref(self) -> int:
        q = select(func.count(ProductRef.id))
        return int((await self.session.execute(q)).scalar_one())

    async def list_ref(self, *, offset: int, limit: int) -> list[ProductRef]:
        q = (
            select(ProductRef)
            .order_by(ProductRef.name.asc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.execute(q)).scalars().all())

    async def get_with_synonyms(self, product_id: uuid.UUID) -> Optional[ProductWithSynonyms]:
        prod = await self.get_product(product_id)
        if not prod:
            return None
        q = select(ProductSynonym.synonym).where(ProductSynonym.product_ref_id == product_id).order_by(ProductSynonym.synonym.asc())
        syns = [str(x) for x in (await self.session.execute(q)).scalars().all()]
        return ProductWithSynonyms(product=prod, synonyms=syns)

    async def create_ref(
        self,
        *,
        name: str,
        kcal_per_100g: float,
        protein_100g: float | None = None,
        fat_100g: float | None = None,
        carbs_100g: float | None = None,
        brand: str | None = None,
        synonyms: Sequence[str] = (),
    ) -> ProductRef:
        prod = ProductRef(
            name=name,
            brand=brand,
            kcal_per_100g=kcal_per_100g,
            protein_100g=protein_100g,
            fat_100g=fat_100g,
            carbs_100g=carbs_100g,
        )
        self.session.add(prod)
        await self.session.flush()

        await self.replace_synonyms(prod.id, synonyms)
        return prod

    async def update_ref(
        self,
        product_id: uuid.UUID,
        *,
        name: str,
        kcal_per_100g: float,
        protein_100g: float | None = None,
        fat_100g: float | None = None,
        carbs_100g: float | None = None,
        brand: str | None = None,
        synonyms: Sequence[str] = (),
    ) -> None:
        prod = await self.get_product(product_id)
        if not prod:
            return
        prod.name = name
        prod.brand = brand
        prod.kcal_per_100g = kcal_per_100g
        prod.protein_100g = protein_100g
        prod.fat_100g = fat_100g
        prod.carbs_100g = carbs_100g

        await self.replace_synonyms(product_id, synonyms)

    async def delete_ref(self, product_id: uuid.UUID) -> None:
        # синонимы каскадно удалятся, но можно и явно
        await self.session.execute(delete(ProductRef).where(ProductRef.id == product_id))

    async def replace_synonyms(self, product_id: uuid.UUID, synonyms: Sequence[str]) -> None:
        # удаляем старые
        await self.session.execute(delete(ProductSynonym).where(ProductSynonym.product_ref_id == product_id))

        # вставляем новые
        cleaned = []
        seen = set()
        for s in synonyms:
            ss = s.strip()
            if not ss:
                continue
            key = ss.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(ss)

        for s in cleaned:
            self.session.add(ProductSynonym(product_ref_id=product_id, synonym=s))

        await self.session.flush()

    async def exists_by_names_exact(self, names: Sequence[str]) -> set[str]:
        """
        Проверяет exact match по products_ref.name (CITEXT — case-insensitive).
        Возвращает множество имен, которые существуют (в исходном виде из БД).
        """
        cleaned = [n.strip() for n in names if n and n.strip()]
        if not cleaned:
            return set()

        q = select(ProductRef.name).where(ProductRef.name.in_(cleaned))
        rows = [str(x) for x in (await self.session.execute(q)).scalars().all()]
        # rows будут в “каноническом” виде из БД
        return set(rows)
    
    async def find_exact_product(self, text: str) -> ProductRef | None:
        """
        1) exact match по products_ref.name (CITEXT -> case-insensitive)
        2) если не найдено — exact match по product_synonyms.synonym -> связанный product_ref
        """
        q = (text or "").strip()
        if not q:
            return None

        # 1) exact name
        r1 = (await self.session.execute(select(ProductRef).where(ProductRef.name == q))).scalars().first()
        if r1:
            return r1

        # 2) exact synonym
        r2 = (
            await self.session.execute(
                select(ProductRef)
                .select_from(ProductSynonym)
                .join(ProductRef, ProductRef.id == ProductSynonym.product_ref_id)
                .where(ProductSynonym.synonym == q)
                .order_by(ProductRef.name.asc())
                .limit(1)
            )
        ).scalars().first()

        return r2
