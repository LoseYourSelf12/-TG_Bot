from __future__ import annotations

import math
import uuid
from typing import Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.bot.states_admin import AdminProductsFlow
from app.bot.utils.panel import edit_panel_from_callback, ensure_panel
from app.db.repo_products import ProductRepo
from app.bot.keyboards.admin_products import (
    products_list_kb,
    product_card_kb,
    product_delete_confirm_kb,
    missing_synonyms_kb,
    input_add_kb,
    input_edit_kb,
    ProductRow,
    APListCb,
    APOpenCb,
    APAddCb,
    APEditCb,
    APDelAskCb,
    APDelConfCb,
    APMissAllCb,
    APCancelAddCb,
    APCancelEditCb,
)
from app.bot.utils.ids import short_to_uuid


router = Router()

PAGE_SIZE = 10


def _is_admin(tg_user_id: int) -> bool:
    return tg_user_id in settings.admin_ids


def _parse_line(line: str) -> tuple[str, float, list[str], Optional[float], Optional[float], Optional[float], Optional[str]]:
    """
    Формат:
      name | kcal_per_100g | synonyms(comma) | protein | fat | carbs | brand
    """
    parts = [p.strip() for p in (line or "").split("|")]
    while len(parts) < 7:
        parts.append("")

    name = parts[0].strip()
    if not name:
        raise ValueError("Пустое имя продукта")

    kcal = float(parts[1].replace(",", ".").strip())
    if kcal < 0:
        raise ValueError("Калории должны быть >= 0")

    synonyms = [s.strip() for s in parts[2].split(",") if s.strip()]

    def fopt(x: str) -> Optional[float]:
        x = x.strip()
        if not x:
            return None
        v = float(x.replace(",", "."))
        if v < 0:
            raise ValueError("БЖУ должны быть >= 0")
        return v

    protein = fopt(parts[3])
    fat = fopt(parts[4])
    carbs = fopt(parts[5])
    brand = parts[6].strip() or None

    return name, kcal, synonyms, protein, fat, carbs, brand


def _product_card_text(
    name: str,
    kcal: float,
    syns: list[str],
    protein: Optional[float],
    fat: Optional[float],
    carbs: Optional[float],
    brand: Optional[str],
) -> str:
    syn_line = ", ".join(syns) if syns else "—"
    return (
        f"📦 Продукт\n\n"
        f"Название: {name}\n"
        f"Ккал/100г: {kcal:.2f}\n"
        f"Белки/100г: {protein if protein is not None else '—'}\n"
        f"Жиры/100г: {fat if fat is not None else '—'}\n"
        f"Углеводы/100г: {carbs if carbs is not None else '—'}\n"
        f"Бренд: {brand or '—'}\n\n"
        f"Синонимы: {syn_line}\n"
    )


async def _render_list(cq: CallbackQuery, session: AsyncSession, page: int) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа", show_alert=True)
        return

    repo = ProductRepo(session)
    total = await repo.count_ref()
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(total_pages, page))

    offset = (page - 1) * PAGE_SIZE
    prods = await repo.list_ref(offset=offset, limit=PAGE_SIZE)
    rows = [
        ProductRow(
            id=p.id,
            name=str(p.name),
            kcal_per_100g=float(p.kcal_per_100g),
            complete=(p.kcal_per_100g is not None and p.protein_100g is not None and p.fat_100g is not None and p.carbs_100g is not None),
        )
        for p in prods
    ]

    kb = products_list_kb(page=page, total_pages=total_pages, total_count=total, rows=rows)
    await edit_panel_from_callback(cq, "🛠 Справочник продуктов\n\nВыбери продукт или добавь новый:", kb)


async def _render_card(cq: CallbackQuery, session: AsyncSession, product_id: uuid.UUID, back_page: int) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа", show_alert=True)
        return

    repo = ProductRepo(session)
    data = await repo.get_with_synonyms(product_id)
    if not data:
        await cq.answer("Не найдено", show_alert=True)
        return

    p = data.product
    text = _product_card_text(
        name=str(p.name),
        kcal=float(p.kcal_per_100g),
        syns=data.synonyms,
        protein=float(p.protein_100g) if p.protein_100g is not None else None,
        fat=float(p.fat_100g) if p.fat_100g is not None else None,
        carbs=float(p.carbs_100g) if p.carbs_100g is not None else None,
        brand=str(p.brand) if p.brand is not None else None,
    )
    await edit_panel_from_callback(cq, text, product_card_kb(product_id, back_page))


async def _after_save_show_missing_or_card(
    *,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    product_id: uuid.UUID,
    back_page: int,
) -> None:
    repo = ProductRepo(session)
    data = await repo.get_with_synonyms(product_id)
    if not data:
        await ensure_panel(bot=message.bot, chat_id=message.chat.id, state=state, text="Не найдено", reply_markup=None)
        return

    p = data.product
    syns = data.synonyms

    existing = await repo.exists_by_names_exact(syns)
    existing_casefold = {e.casefold() for e in existing}
    missing = [s for s in syns if s.casefold() not in existing_casefold]

    text = _product_card_text(
        name=str(p.name),
        kcal=float(p.kcal_per_100g),
        syns=syns,
        protein=float(p.protein_100g) if p.protein_100g is not None else None,
        fat=float(p.fat_100g) if p.fat_100g is not None else None,
        carbs=float(p.carbs_100g) if p.carbs_100g is not None else None,
        brand=str(p.brand) if p.brand is not None else None,
    )

    if missing:
        missing_list = "\n".join(f"• {x}" for x in missing)
        await ensure_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            state=state,
            text=(
                text
                + "\n⚠️ Эти синонимы не существуют как отдельные продукты в справочнике:\n"
                + missing_list
                + "\n\nДобавить их как продукты? (ккал/100г возьмём как у текущего продукта)"
            ),
            reply_markup=missing_synonyms_kb(product_id, back_page, len(missing)),
        )
    else:
        await ensure_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            state=state,
            text=text,
            reply_markup=product_card_kb(product_id, back_page),
        )


# ----- LIST -----
@router.callback_query(APListCb.filter())
async def admin_products_list(cq: CallbackQuery, callback_data: APListCb, session: AsyncSession):
    await _render_list(cq, session, callback_data.page)


# ----- OPEN -----
@router.callback_query(APOpenCb.filter())
async def admin_products_open(cq: CallbackQuery, callback_data: APOpenCb, session: AsyncSession):
    await _render_card(cq, session, short_to_uuid(callback_data.pid), callback_data.page)


# ----- ADD -----
@router.callback_query(APAddCb.filter())
async def admin_products_add_start(cq: CallbackQuery, callback_data: APAddCb, state: FSMContext):
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа", show_alert=True)
        return

    back_page = callback_data.page
    await state.update_data(admin_back_page=back_page)
    await state.set_state(AdminProductsFlow.waiting_add_line)

    await edit_panel_from_callback(
        cq,
        "➕ Добавление продукта\n\n"
        "Введи строку в формате:\n"
        "<продукт> | <ккал/100г> | <синонимы через запятую> | <белки> | <жиры> | <углеводы> | <бренд>\n\n"
        "Пример:\n"
        "Макароны из твердых сортов | 350 | макароны, спагетти, лапша | 12 | 2 | 70 | Barilla",
        reply_markup=input_add_kb(back_page),
    )


@router.callback_query(AdminProductsFlow.waiting_add_line, APCancelAddCb.filter())
async def admin_add_cancel(cq: CallbackQuery, callback_data: APCancelAddCb, state: FSMContext, session: AsyncSession):
    await state.set_state(None)
    await _render_list(cq, session, callback_data.page)


@router.message(AdminProductsFlow.waiting_add_line)
async def admin_products_add_submit(message: Message, state: FSMContext, session: AsyncSession):
    if not _is_admin(message.from_user.id):
        return

    try:
        name, kcal, syns, protein, fat, carbs, brand = _parse_line(message.text or "")
    except Exception as e:
        await ensure_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            state=state,
            text=f"Ошибка формата: {e}\n\nПопробуй ещё раз:",
            reply_markup=None,
        )
        return

    repo = ProductRepo(session)
    prod = await repo.create_ref(
        name=name,
        kcal_per_100g=kcal,
        protein_100g=protein,
        fat_100g=fat,
        carbs_100g=carbs,
        brand=brand,
        synonyms=syns,
    )

    back_page = int((await state.get_data()).get("admin_back_page", 1))
    await state.set_state(None)

    await _after_save_show_missing_or_card(
        message=message,
        state=state,
        session=session,
        product_id=prod.id,
        back_page=back_page,
    )


# ----- EDIT -----
@router.callback_query(APEditCb.filter())
async def admin_products_edit_start(cq: CallbackQuery, callback_data: APEditCb, state: FSMContext, session: AsyncSession):
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа", show_alert=True)
        return

    product_id = short_to_uuid(callback_data.pid)
    back_page = callback_data.page

    repo = ProductRepo(session)
    data = await repo.get_with_synonyms(product_id)
    if not data:
        await cq.answer("Не найдено", show_alert=True)
        return

    p = data.product
    syn_line = ", ".join(data.synonyms)

    current_line = (
        f"{p.name} | {float(p.kcal_per_100g):g} | {syn_line} | "
        f"{(float(p.protein_100g) if p.protein_100g is not None else '')} | "
        f"{(float(p.fat_100g) if p.fat_100g is not None else '')} | "
        f"{(float(p.carbs_100g) if p.carbs_100g is not None else '')} | "
        f"{(p.brand or '')}"
    )

    await state.update_data(admin_edit_product_id=str(product_id), admin_back_page=back_page)
    await state.set_state(AdminProductsFlow.waiting_edit_line)

    await edit_panel_from_callback(
        cq,
        "✏️ Редактирование продукта\n\n"
        "Введи строку в формате:\n"
        "<продукт> | <ккал/100г> | <синонимы> | <белки> | <жиры> | <углеводы> | <бренд>\n\n"
        f"Текущая строка (можно скопировать и править):\n{current_line}",
        reply_markup=input_edit_kb(product_id, back_page),
    )


@router.callback_query(AdminProductsFlow.waiting_edit_line, APCancelEditCb.filter())
async def admin_edit_cancel(cq: CallbackQuery, callback_data: APCancelEditCb, state: FSMContext, session: AsyncSession):
    product_id = short_to_uuid(callback_data.pid)
    back_page = callback_data.page
    await state.set_state(None)
    await _render_card(cq, session, product_id, back_page)


@router.message(AdminProductsFlow.waiting_edit_line)
async def admin_products_edit_submit(message: Message, state: FSMContext, session: AsyncSession):
    if not _is_admin(message.from_user.id):
        return

    data_state = await state.get_data()
    product_id = uuid.UUID(data_state["admin_edit_product_id"])
    back_page = int(data_state.get("admin_back_page", 1))

    try:
        name, kcal, syns, protein, fat, carbs, brand = _parse_line(message.text or "")
    except Exception as e:
        await ensure_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            state=state,
            text=f"Ошибка формата: {e}\n\nПопробуй ещё раз:",
            reply_markup=None,
        )
        return

    repo = ProductRepo(session)
    await repo.update_ref(
        product_id,
        name=name,
        kcal_per_100g=kcal,
        protein_100g=protein,
        fat_100g=fat,
        carbs_100g=carbs,
        brand=brand,
        synonyms=syns,
    )

    await state.set_state(None)

    await _after_save_show_missing_or_card(
        message=message,
        state=state,
        session=session,
        product_id=product_id,
        back_page=back_page,
    )


# ----- DELETE -----
@router.callback_query(APDelAskCb.filter())
async def admin_products_delete_ask(cq: CallbackQuery, callback_data: APDelAskCb, session: AsyncSession):
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа", show_alert=True)
        return

    product_id = short_to_uuid(callback_data.pid)
    back_page = callback_data.page

    await edit_panel_from_callback(
        cq,
        "Точно удалить продукт? Это удалит и все его синонимы.",
        product_delete_confirm_kb(product_id, back_page),
    )


@router.callback_query(APDelConfCb.filter())
async def admin_products_delete_confirm(cq: CallbackQuery, callback_data: APDelConfCb, session: AsyncSession):
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа", show_alert=True)
        return

    product_id = short_to_uuid(callback_data.pid)
    back_page = callback_data.page

    repo = ProductRepo(session)
    await repo.delete_ref(product_id)

    await _render_list(cq, session, back_page)


# ----- ADD MISSING SYNONYMS AS PRODUCTS -----
@router.callback_query(APMissAllCb.filter())
async def admin_products_add_missing_all(cq: CallbackQuery, callback_data: APMissAllCb, session: AsyncSession):
    if not _is_admin(cq.from_user.id):
        await cq.answer("Нет доступа", show_alert=True)
        return

    product_id = short_to_uuid(callback_data.pid)
    back_page = callback_data.page

    repo = ProductRepo(session)
    data = await repo.get_with_synonyms(product_id)
    if not data:
        await cq.answer("Не найдено", show_alert=True)
        return

    p = data.product
    syns = data.synonyms

    existing = await repo.exists_by_names_exact(syns)
    existing_casefold = {e.casefold() for e in existing}
    missing = [s for s in syns if s.casefold() not in existing_casefold]

    created = 0
    for name in missing:
        await repo.create_ref(
            name=name,
            kcal_per_100g=float(p.kcal_per_100g),
            protein_100g=None,
            fat_100g=None,
            carbs_100g=None,
            brand=None,
            synonyms=(),
        )
        created += 1

    await cq.answer(f"Добавлено: {created}", show_alert=True)
    await _render_card(cq, session, product_id, back_page)
