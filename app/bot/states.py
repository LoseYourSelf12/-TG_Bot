from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddMealFlow(StatesGroup):
    picking_date = State()
    picking_time = State()
    typing_custom_time = State()

    typing_items = State()

    mapping_item = State()
    typing_grams = State()

    waiting_photo = State()
