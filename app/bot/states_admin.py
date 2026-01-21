from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AdminProductsFlow(StatesGroup):
    waiting_add_line = State()
    waiting_edit_line = State()
