"""Handlers package — exports combined router."""
from aiogram import Router
from .user import router as user_router
from .admin import router as admin_router

router = Router()
router.include_router(user_router)
router.include_router(admin_router)

__all__ = ["router"]
