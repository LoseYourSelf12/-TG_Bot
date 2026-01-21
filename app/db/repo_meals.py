from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select, delete, and_, text, func, outerjoin
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Meal, MealItem, MealPhoto, ProductRef


@dataclass(frozen=True)
class DayMark:
    meals_count: int
    photos_count: int
    kcal_total: float


@dataclass(frozen=True)
class MealItemView:
    id: uuid.UUID
    position: int
    raw_name: str
    grams: float | None
    kcal_total: float | None
    product_ref_id: uuid.UUID | None
    product_name: str | None


class MealRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_meal(self, user_id: uuid.UUID, meal_date: date, meal_time: time, note: Optional[str] = None) -> Meal:
        meal = Meal(user_id=user_id, meal_date=meal_date, meal_time=meal_time, note=note)
        self.session.add(meal)
        await self.session.flush()
        return meal

    async def delete_meal(self, meal_id: uuid.UUID) -> None:
        await self.session.execute(delete(Meal).where(Meal.id == meal_id))

    async def get_meal(self, meal_id: uuid.UUID) -> Optional[Meal]:
        q = select(Meal).where(Meal.id == meal_id)
        return (await self.session.execute(q)).scalars().first()

    async def list_meals_by_day(self, user_id: uuid.UUID, day: date) -> List[Meal]:
        q = (
            select(Meal)
            .where(and_(Meal.user_id == user_id, Meal.meal_date == day))
            .order_by(Meal.meal_time.asc())
        )
        return list((await self.session.execute(q)).scalars().all())

    async def create_items_for_meal(self, meal_id: uuid.UUID, raw_items: list[str]) -> List[MealItem]:
        items: list[MealItem] = []
        for idx, raw in enumerate(raw_items, start=1):
            item = MealItem(meal_id=meal_id, position=idx, raw_name=raw)
            self.session.add(item)
            items.append(item)
        await self.session.flush()
        return items

    async def list_items(self, meal_id: uuid.UUID) -> List[MealItem]:
        q = select(MealItem).where(MealItem.meal_id == meal_id).order_by(MealItem.position.asc())
        return list((await self.session.execute(q)).scalars().all())
    
    async def list_items_view(self, meal_id: uuid.UUID) -> list[MealItemView]:
        """
        Возвращает позиции приёма пищи + имя продукта из справочника (если выбрано).
        """
        j = outerjoin(MealItem, ProductRef, MealItem.product_ref_id == ProductRef.id)
        q = (
            select(
                MealItem.id,
                MealItem.position,
                MealItem.raw_name,
                MealItem.grams,
                MealItem.kcal_total,
                MealItem.product_ref_id,
                ProductRef.name.label("product_name"),
            )
            .select_from(j)
            .where(MealItem.meal_id == meal_id)
            .order_by(MealItem.position.asc())
        )
        rows = (await self.session.execute(q)).all()
        return [
            MealItemView(
                id=r.id,
                position=r.position,
                raw_name=r.raw_name,
                grams=float(r.grams) if r.grams is not None else None,
                kcal_total=float(r.kcal_total) if r.kcal_total is not None else None,
                product_ref_id=r.product_ref_id,
                product_name=str(r.product_name) if r.product_name is not None else None,
            )
            for r in rows
        ]

    async def get_item(self, item_id: uuid.UUID) -> Optional[MealItem]:
        q = select(MealItem).where(MealItem.id == item_id)
        return (await self.session.execute(q)).scalars().first()

    async def set_item_product(self, item_id: uuid.UUID, product_ref_id: Optional[uuid.UUID]) -> None:
        item = await self.get_item(item_id)
        if item is None:
            raise ValueError(f"MealItem not found: {item_id}")
        item.product_ref_id = product_ref_id
        item.user_product_id = None

    async def set_item_grams_and_kcal(self, item_id: uuid.UUID, grams: float) -> None:
        item = await self.get_item(item_id)
        if item is None:
            return
        item.grams = grams

        kcal_total = None
        if item.product_ref_id is not None:
            prod = (await self.session.execute(select(ProductRef).where(ProductRef.id == item.product_ref_id))).scalars().first()
            if prod is not None:
                kcal_total = float(prod.kcal_per_100g) * float(grams) / 100.0

        item.kcal_total = kcal_total

    async def add_photo(
        self,
        meal_id: uuid.UUID,
        tg_file_id: str,
        tg_file_unique_id: Optional[str],
        local_path: Optional[str],
        mime_type: Optional[str],
        width: Optional[int],
        height: Optional[int],
        file_size_bytes: Optional[int],
    ) -> MealPhoto:
        ph = MealPhoto(
            meal_id=meal_id,
            tg_file_id=tg_file_id,
            tg_file_unique_id=tg_file_unique_id,
            local_path=local_path,
            mime_type=mime_type,
            width=width,
            height=height,
            file_size_bytes=file_size_bytes,
        )
        self.session.add(ph)
        await self.session.flush()
        return ph

    async def list_photos(self, meal_id: uuid.UUID) -> List[MealPhoto]:
        q = select(MealPhoto).where(MealPhoto.meal_id == meal_id).order_by(MealPhoto.created_at.asc())
        return list((await self.session.execute(q)).scalars().all())

    async def month_marks(self, user_id: uuid.UUID, start: date, end: date) -> Dict[date, DayMark]:
        """
        Берем агрегаты из nutrition_bot.v_day_stats (view создан в SQL).
        """
        q = text(
            """
            SELECT meal_date, meals_count, kcal_total, photos_count
            FROM nutrition_bot.v_day_stats
            WHERE user_id = :user_id
              AND meal_date >= :start_date
              AND meal_date <= :end_date
            """
        )
        rows = (await self.session.execute(q, {"user_id": str(user_id), "start_date": start, "end_date": end})).all()

        result: Dict[date, DayMark] = {}
        for r in rows:
            result[r.meal_date] = DayMark(
                meals_count=int(r.meals_count or 0),
                photos_count=int(r.photos_count or 0),
                kcal_total=float(r.kcal_total or 0.0),
            )
        return result
    
    async def range_summary(self, user_id: uuid.UUID, start: date, end: date) -> tuple[list[date], list[float], float, int, int]:
        """
        Возвращает:
        - dates (все дни диапазона)
        - kcal_values по дням (0 если нет)
        - total_kcal
        - total_meals
        - total_photos
        """
        marks = await self.month_marks(user_id, start, end)

        days = []
        kcal_vals = []
        total_kcal = 0.0
        total_meals = 0
        total_photos = 0

        d = start
        while d <= end:
            days.append(d)
            m = marks.get(d)
            kcal = float(m.kcal_total) if m else 0.0
            meals = int(m.meals_count) if m else 0
            photos = int(m.photos_count) if m else 0

            kcal_vals.append(kcal)
            total_kcal += kcal
            total_meals += meals
            total_photos += photos
            d += timedelta(days=1)

        return days, kcal_vals, total_kcal, total_meals, total_photos
