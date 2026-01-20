from __future__ import annotations

from typing import Optional

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest


PANEL_KEY = "panel_message_id"


def _is_not_modified(err: Exception) -> bool:
    return isinstance(err, TelegramBadRequest) and "message is not modified" in str(err).lower()


async def ensure_panel(
    *,
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> int:
    data = await state.get_data()
    panel_id = data.get(PANEL_KEY)

    if panel_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(panel_id),
                text=text,
                reply_markup=reply_markup,
            )
            return int(panel_id)
        except Exception as e:
            if _is_not_modified(e):
                return int(panel_id)
            # Если сообщение нельзя редактировать (удалено/старое) — создадим новое
            pass

    msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    await state.update_data(**{PANEL_KEY: msg.message_id})
    return msg.message_id


async def edit_panel_from_callback(
    cq: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    try:
        await cq.message.edit_text(text=text, reply_markup=reply_markup)
    except Exception as e:
        if not _is_not_modified(e):
            raise
    finally:
        await cq.answer()
