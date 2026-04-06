"""APScheduler job definitions."""
import os

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from aiogram.types import BufferedInputFile
from loguru import logger

from excel_report_bot.config import settings
from excel_report_bot.db.database import get_latest_uploads, delete_old_uploads


async def send_scheduled_report(bot: Bot, user_id: int) -> None:
    """Send scheduled report to user; send reminder if no file uploaded."""
    log = logger.bind(user_id=user_id)
    log.info("Sending scheduled report")

    uploads = await get_latest_uploads(settings.DATABASE_PATH, user_id, limit=1)

    if not uploads or not os.path.exists(uploads[0]["file_path"]):
        await bot.send_message(
            user_id,
            "⏰ Напоминание: вы не загрузили файл для отчёта.\n"
            "Используйте /upload чтобы загрузить .xlsx файл.",
        )
        return

    from excel_report_bot.db.database import get_user, save_report
    from excel_report_bot.parser.excel_parser import parse_excel
    from excel_report_bot.utils.formatters import format_brief, format_full
    from excel_report_bot.utils.charts import generate_top_chart

    upload = uploads[0]
    user = await get_user(settings.DATABASE_PATH, user_id)
    report_mode = user["report_mode"] if user else "brief"

    try:
        result = parse_excel(upload["file_path"], upload["original_name"])
    except Exception as e:
        log.error(f"Scheduled report parse error: {e}")
        return  # Log only, no user notification on scheduler failure

    await save_report(
        settings.DATABASE_PATH,
        user_id=user_id,
        file_name=upload["original_name"],
        revenue=result.revenue,
        positions=result.positions,
        avg_check=result.avg_check,
        summary=result.to_summary_dict(),
    )

    if report_mode == "brief":
        await bot.send_message(user_id, format_brief(result), parse_mode="HTML")
    elif report_mode == "full":
        for part in format_full(result):
            await bot.send_message(user_id, part, parse_mode="HTML")
    elif report_mode == "chart":
        for part in format_full(result):
            await bot.send_message(user_id, part, parse_mode="HTML")
        chart = await generate_top_chart(result)
        await bot.send_photo(
            user_id,
            BufferedInputFile(chart.read(), filename="chart.png"),
        )
        from excel_report_bot.utils.charts import generate_daily_chart
        daily_chart = await generate_daily_chart(result)
        if daily_chart:
            await bot.send_photo(
                user_id,
                BufferedInputFile(daily_chart.read(), filename="daily_revenue.png"),
                caption="📅 Выручка по дням",
            )

    # --- Stock alert: send urgent notification if any products are out of stock ---
    if result.zero_stock:
        zero_list = "\n".join(f"  🚫 {name}" for name in result.zero_stock[:10])
        suffix = f"\n  ...и ещё {len(result.zero_stock) - 10}" if len(result.zero_stock) > 10 else ""
        await bot.send_message(
            user_id,
            f"🔴 <b>Критический алерт: нет в наличии!</b>\n\n"
            f"{zero_list}{suffix}\n\n"
            f"Обновите файл через /upload.",
            parse_mode="HTML",
        )
        log.warning(f"Stock alert sent: {len(result.zero_stock)} zero-stock items")

    log.info(f"Scheduled report sent: revenue={result.revenue}")


async def cleanup_old_files(db_path: str, uploads_dir: str) -> None:
    """Delete files and DB records older than FILE_RETENTION_DAYS."""
    paths = await delete_old_uploads(db_path, days=settings.FILE_RETENTION_DAYS)
    removed = 0
    for path in paths:
        if os.path.exists(path):
            try:
                os.remove(path)
                removed += 1
            except OSError as e:
                logger.warning(f"Could not delete {path}: {e}")
    logger.info(f"Cleanup: removed {removed} files, {len(paths)} DB records")


def register_user_job(
    scheduler: AsyncIOScheduler,
    bot: Bot,
    user: dict,
) -> None:
    """Add or replace a scheduled report job for a user."""
    job_id = f"report_{user['user_id']}"
    try:
        hour, minute = user["report_time"].split(":")
        tz = pytz.timezone(user["timezone"])
    except Exception as e:
        logger.warning(f"Invalid schedule settings for user {user['user_id']}: {e}")
        return

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        send_scheduled_report,
        trigger=CronTrigger(hour=int(hour), minute=int(minute), timezone=tz),
        id=job_id,
        kwargs={"bot": bot, "user_id": user["user_id"]},
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info(f"Registered job {job_id} at {user['report_time']} {user['timezone']}")


def register_cleanup_job(
    scheduler: AsyncIOScheduler,
    db_path: str,
    uploads_dir: str,
) -> None:
    """Register daily cleanup job at 03:00 UTC."""
    scheduler.add_job(
        cleanup_old_files,
        trigger=CronTrigger(hour=settings.CLEANUP_HOUR_UTC, minute=0, timezone=pytz.utc),
        id="cleanup_old_files",
        kwargs={"db_path": db_path, "uploads_dir": uploads_dir},
        replace_existing=True,
    )
    logger.info(f"Registered cleanup job at {settings.CLEANUP_HOUR_UTC}:00 UTC")
