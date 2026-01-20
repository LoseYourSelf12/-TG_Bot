from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.menu import main_menu_kb
from app.bot.utils.panel import ensure_panel
from app.bot.utils.text import menu_text
from app.config import settings

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    is_admin = message.from_user.id in settings.admin_ids
    await ensure_panel(
        bot=message.bot,
        chat_id=message.chat.id,
        state=state,
        text=menu_text(),
        reply_markup=main_menu_kb(is_admin=is_admin),
    )
