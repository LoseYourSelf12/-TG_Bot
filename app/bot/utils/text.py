from __future__ import annotations

from datetime import date, time
from typing import Iterable, Optional

from app.db.models import Meal, MealItem, MealPhoto
from app.db.repo_meals import MealItemView


def menu_text() -> str:
    return (
        "Главное меню\n\n"
        "Выбирай действие:"
    )


def calendar_recent_text() -> str:
    return "Быстрый доступ: сегодня и 2 предыдущих дня.\n\nВыбери день:"


def pick_date_text() -> str:
    return "Выбери день в календаре для добавления приема пищи."


def pick_time_text(day: date, selected: Optional[time] = None) -> str:
    s = f"День: {day.isoformat()}\n\nВыбери время приема пищи."
    if selected:
        s += f"\n\nТекущее выбранное: {selected.strftime('%H:%M')}"
    return s


def enter_custom_time_text() -> str:
    return "Введи время в формате ЧЧ:ММ (округлю к ближайшим 15 минутам)."


def enter_items_text(day: date, t: time) -> str:
    return (
        f"День: {day.isoformat()}  Время: {t.strftime('%H:%M')}\n\n"
        "Напиши, что ел (через запятую).\n"
        "Пример: макароны, котлеты, салат"
    )


def map_item_text(raw_item: str, idx: int, total: int) -> str:
    return (
        f"Продукт {idx}/{total}\n\n"
        f"Ты ввел: «{raw_item}»\n\n"
        "Выбери наиболее подходящий продукт из справочника (топ совпадений/синонимов):"
    )


def ask_grams_text(raw_item: str) -> str:
    return f"Сколько съел «{raw_item}»? Введи граммы числом (например 120)."


def photo_step_text(photos_count: int) -> str:
    return (
        "Загрузи фото приема пищи (можно несколько).\n"
        "После загрузки нажми «Готово».\n\n"
        f"Фото добавлено: {photos_count}"
    )


def day_view_text(day: date, meals: Iterable[Meal]) -> str:
    lines = [f"День: {day.isoformat()}", ""]
    meals_list = list(meals)
    if not meals_list:
        lines.append("Записей нет.")
        return "\n".join(lines)

    lines.append("Приемы пищи:")
    for m in meals_list:
        lines.append(f"• {m.meal_time.strftime('%H:%M')}")
    return "\n".join(lines)


def meal_details_text(meal: Meal, items: list[MealItem], photos: list[MealPhoto]) -> str:
    lines = [
        f"Прием пищи: {meal.meal_date.isoformat()} {meal.meal_time.strftime('%H:%M')}",
        "",
    ]
    if meal.note:
        lines.append(f"Описание: {meal.note}")
        lines.append("")

    if items:
        lines.append("Позиции:")
        for it in items:
            grams = f"{float(it.grams):g} г" if it.grams is not None else "—"
            kcal = f"{float(it.kcal_total):g} ккал" if it.kcal_total is not None else "—"
            mapped = "✅" if it.product_ref_id else "❔"
            lines.append(f"• {mapped} {it.raw_name} — {grams} — {kcal}")
        lines.append("")
    lines.append(f"Фото: {len(photos)}")
    return "\n".join(lines)


def meal_details_text_view(meal: Meal, items: list[MealItemView], photos: list[MealPhoto]) -> str:
    lines = [
        f"Прием пищи: {meal.meal_date.isoformat()} {meal.meal_time.strftime('%H:%M')}",
        "",
    ]
    if meal.note:
        lines.append(f"Описание: {meal.note}")
        lines.append("")

    if items:
        lines.append("Позиции:")
        for it in items:
            grams = f"{it.grams:g} г" if it.grams is not None else "—"
            kcal = f"{it.kcal_total:g} ккал" if it.kcal_total is not None else "—"

            if it.product_ref_id and it.product_name:
                if it.product_name.casefold() == it.raw_name.casefold():
                    name_line = f"✅ {it.product_name}"
                else:
                    name_line = f"✅ {it.product_name} (ввели: {it.raw_name})"
            else:
                name_line = f"❔ {it.raw_name}"

            lines.append(f"• {name_line} — {grams} — {kcal}")
        lines.append("")
    lines.append(f"Фото: {len(photos)}")
    return "\n".join(lines)
