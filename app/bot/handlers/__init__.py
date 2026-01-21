from aiogram import Router

from .start import router as start_router
from .menu import router as menu_router
from .add_meal import router as add_meal_router
from .day_view import router as day_view_router
from .stats import router as stats_router
from .admin_products import router as admin_products_router
from .noop import router as noop_router


def build_router() -> Router:
    r = Router()
    r.include_router(start_router)
    r.include_router(menu_router)
    r.include_router(add_meal_router)
    r.include_router(stats_router)
    r.include_router(day_view_router)
    r.include_router(admin_products_router)
    r.include_router(noop_router)
    return r
