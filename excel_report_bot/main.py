"""Entry point — starts bot, scheduler, and FastAPI in one asyncio event loop."""
import asyncio
import os
import sys
from datetime import datetime, timezone

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from excel_report_bot.config import settings
from excel_report_bot.db.database import init_db, get_scheduled_users

# Global scheduler — accessed by handlers for reschedule on settings change
scheduler: AsyncIOScheduler = AsyncIOScheduler()


def setup_logging() -> None:
    """Configure loguru — file rotation + stderr."""
    os.makedirs(settings.LOGS_DIR, exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
    )
    logger.add(
        f"{settings.LOGS_DIR}/bot.log",
        level=settings.LOG_LEVEL,
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
        encoding="utf-8",
    )


async def on_startup(bot: Bot) -> None:
    """Initialize DB, set start time, restore scheduler jobs."""
    from excel_report_bot.api.health import set_start_time
    set_start_time(datetime.now(timezone.utc))

    logger.info("Bot starting up")
    await init_db(settings.DATABASE_PATH)
    logger.info(f"Database initialized at {settings.DATABASE_PATH}")

    from excel_report_bot.scheduler.jobs import register_user_job, register_cleanup_job
    register_cleanup_job(scheduler, settings.DATABASE_PATH, settings.UPLOADS_DIR)

    users = await get_scheduled_users(settings.DATABASE_PATH)
    for user in users:
        register_user_job(scheduler, bot, user)
    logger.info(f"Restored {len(users)} scheduler jobs")

    scheduler.start()
    logger.info("Scheduler started")


async def on_shutdown(bot: Bot) -> None:
    """Graceful shutdown — stop scheduler and close bot session."""
    logger.info("Bot shutting down")
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await bot.session.close()


async def start_bot() -> None:
    """Start aiogram polling."""
    from excel_report_bot.bot.handlers import router
    from excel_report_bot.bot.middlewares import AuthMiddleware

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp.update.middleware(AuthMiddleware())
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting bot polling")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def start_api() -> None:
    """Start FastAPI health server."""
    from excel_report_bot.api.health import app

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.HEALTH_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.config.install_signal_handlers = False
    logger.info(f"Starting health API on port {settings.HEALTH_PORT}")
    await server.serve()


async def main() -> None:
    """Run bot and health API concurrently."""
    setup_logging()
    await asyncio.gather(
        start_bot(),
        start_api(),
    )


if __name__ == "__main__":
    asyncio.run(main())
