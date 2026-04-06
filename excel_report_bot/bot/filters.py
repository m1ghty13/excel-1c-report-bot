"""Custom aiogram filters."""
from aiogram.filters import BaseFilter
from aiogram.types import Message

from excel_report_bot.config import settings


class IsAdmin(BaseFilter):
    """Pass only if message sender is in ADMIN_IDS."""

    async def __call__(self, message: Message) -> bool:
        """Return True if user is admin."""
        return (
            message.from_user is not None
            and message.from_user.id in settings.admin_ids
        )
