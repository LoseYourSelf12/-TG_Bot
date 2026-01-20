from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, time
from typing import Dict, List, Optional

from sqlalchemy import select, delete, and_, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Meal, MealItem, MealPhoto, ProductRef


@dataclass(frozen=True)
class DayMark:
    meals_count: int
    photos_count: int
    kcal_total: float


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

    async def get_item(self, item_id: uuid.UUID) -> Optional[MealItem]:
        q = select(MealItem).where(MealItem.id == item_id)
        return (await self.session.execute(q)).scalars().first()

    async def set_item_product(self, item_id: uuid.UUID, product_ref_id: Optional[uuid.UUID]) -> None:
        item = await self.get_item(item_id)
        if item is None:
            return
        item.product_ref_id = product_ref_id
        item.user_product_id = None  # MVP
        # kcal_total пересчитаем после ввода grams

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
