"""AuthMiddleware — block users not in ALLOWED_USERS whitelist."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from loguru import logger

from excel_report_bot.config import settings

_DENY_MSG = (
    "⛔ У вас нет доступа к этому боту.\n"
    "Обратитесь к администратору."
)


class AuthMiddleware(BaseMiddleware):
    """Reject updates from users not in ALLOWED_USERS."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Check user_id against whitelist before passing to handler."""
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        if user.id not in settings.allowed_users:
            logger.warning(f"Blocked unauthorized user {user.id} (@{user.username})")
            bot = data.get("bot")
            if bot and isinstance(event, Update) and event.message:
                await event.message.answer(_DENY_MSG)
            return  # Do not call handler

        return await handler(event, data)
