from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery

router = Router()

@router.callback_query(F.data.startswith("noop:"))
async def noop_any(cq: CallbackQuery):
    await cq.answer()
