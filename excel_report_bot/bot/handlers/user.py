"""User-facing command handlers: /start /report /upload /history /settings /compare /cancel."""
import json
import os
import time

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, Document, BufferedInputFile
from loguru import logger

from excel_report_bot.config import settings
from excel_report_bot.db.database import (
    upsert_user,
    get_user,
    save_report,
    get_user_reports,
    get_report_by_id,
    save_upload,
    get_latest_uploads,
    update_user_settings,
)
from excel_report_bot.parser.validators import validate_file
from excel_report_bot.parser.excel_parser import parse_excel, ParseResult
from excel_report_bot.utils.formatters import format_brief, format_full, format_compare, format_export
from excel_report_bot.utils.charts import generate_top_chart, generate_daily_chart
from excel_report_bot.bot.keyboards import (
    main_menu_kb,
    report_inline_kb,
    history_inline_kb,
    settings_inline_kb,
    report_mode_kb,
    timezone_kb,
)

router = Router()


class UploadStates(StatesGroup):
    """FSM states for /upload flow."""
    waiting_for_file = State()


class SettingsStates(StatesGroup):
    """FSM states for /settings time input."""
    waiting_for_time = State()


# ── /start ───────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Handle /start — register user and show main menu."""
    user = message.from_user
    role = "admin" if user.id in settings.admin_ids else "viewer"
    await upsert_user(settings.DATABASE_PATH, user_id=user.id, username=user.username, role=role)
    logger.bind(user_id=user.id).info(f"/start from @{user.username}")

    await message.answer(
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        "Я помогу вам анализировать продажи из Excel.\n\n"
        "Загрузите .xlsx файл командой /upload, затем запросите отчёт через /report.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


# ── /report ──────────────────────────────────────────────────────────────────

async def _send_report(message: Message, user_id: int) -> None:
    """Parse latest uploaded file and send formatted report."""
    uploads = await get_latest_uploads(settings.DATABASE_PATH, user_id, limit=1)
    if not uploads:
        await message.answer(
            "⚠️ Файл не загружен. Используйте /upload чтобы загрузить .xlsx файл."
        )
        return

    upload = uploads[0]
    if not os.path.exists(upload["file_path"]):
        await message.answer("❌ Файл не найден на сервере. Пожалуйста, загрузите файл заново.")
        return

    user = await get_user(settings.DATABASE_PATH, user_id)
    report_mode = user["report_mode"] if user else "brief"

    try:
        result = parse_excel(upload["file_path"], upload["original_name"])
    except Exception as e:
        logger.bind(user_id=user_id).error(f"Parse error: {e}")
        await message.answer(
            f"❌ Ошибка при разборе файла:\n<code>{e}</code>", parse_mode="HTML"
        )
        # Notify admin
        await _notify_admin(message.bot, f"Parse error for user {user_id}: {e}")
        return

    await save_report(
        settings.DATABASE_PATH,
        user_id=user_id,
        file_name=upload["original_name"],
        revenue=result.revenue,
        positions=result.positions,
        avg_check=result.avg_check,
        summary=result.to_summary_dict(),
    )
    logger.bind(user_id=user_id).info(f"Report generated: revenue={result.revenue}")

    if report_mode == "brief":
        await message.answer(
            format_brief(result), reply_markup=report_inline_kb(), parse_mode="HTML"
        )
    elif report_mode == "full":
        for part in format_full(result):
            await message.answer(part, parse_mode="HTML")
        await message.answer("—", reply_markup=report_inline_kb())
    elif report_mode == "chart":
        for part in format_full(result):
            await message.answer(part, parse_mode="HTML")
        chart = await generate_top_chart(result)
        await message.answer_photo(
            BufferedInputFile(chart.read(), filename="top_products.png"),
        )
        daily_chart = await generate_daily_chart(result)
        if daily_chart:
            await message.answer_photo(
                BufferedInputFile(daily_chart.read(), filename="daily_revenue.png"),
                caption="📅 Выручка по дням",
                reply_markup=report_inline_kb(),
            )
        else:
            await message.answer("—", reply_markup=report_inline_kb())


async def _notify_admin(bot: Bot, text: str) -> None:
    """Send error notification to first admin."""
    try:
        admin_ids = settings.admin_ids
        if admin_ids:
            await bot.send_message(admin_ids[0], f"⚠️ Ошибка бота:\n{text}")
    except Exception:
        pass


@router.message(Command("report"))
@router.message(F.text == "📊 Отчёт")
async def cmd_report(message: Message) -> None:
    """Handle /report — send analytics for last uploaded file."""
    logger.bind(user_id=message.from_user.id).info("/report")
    await _send_report(message, message.from_user.id)


@router.callback_query(F.data == "report:refresh")
async def cb_report_refresh(callback: CallbackQuery) -> None:
    """Refresh report via inline button."""
    await callback.answer("Обновляю...")
    await _send_report(callback.message, callback.from_user.id)


@router.callback_query(F.data == "report:download")
async def cb_report_download(callback: CallbackQuery) -> None:
    """Send original xlsx file via inline button."""
    await callback.answer()
    uploads = await get_latest_uploads(settings.DATABASE_PATH, callback.from_user.id, limit=1)
    if not uploads or not os.path.exists(uploads[0]["file_path"]):
        await callback.message.answer("❌ Файл не найден.")
        return
    u = uploads[0]
    with open(u["file_path"], "rb") as f:
        await callback.message.answer_document(
            BufferedInputFile(f.read(), filename=u["original_name"])
        )


# ── /upload ──────────────────────────────────────────────────────────────────

@router.message(Command("upload"))
@router.message(F.text == "📤 Загрузить файл")
async def cmd_upload(message: Message, state: FSMContext) -> None:
    """Prompt user to send xlsx file."""
    await state.set_state(UploadStates.waiting_for_file)
    logger.bind(user_id=message.from_user.id).info("/upload initiated")
    await message.answer(
        "📎 Пришлите .xlsx файл (до 10 MB).\n"
        "Отправьте /cancel для отмены."
    )


@router.message(UploadStates.waiting_for_file, F.document)
async def handle_document(message: Message, state: FSMContext, bot: Bot) -> None:
    """Receive and validate xlsx document during upload state."""
    await state.clear()
    doc: Document = message.document
    user_id = message.from_user.id
    log = logger.bind(user_id=user_id)

    os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
    timestamp = int(time.time())
    safe_name = doc.file_name.replace("/", "_").replace("\\", "_")
    file_path = os.path.join(settings.UPLOADS_DIR, f"{user_id}_{timestamp}_{safe_name}")

    await bot.download(doc, destination=file_path)
    log.info(f"Downloaded: {file_path} ({doc.file_size} bytes)")

    ok, msg = validate_file(file_path, settings.MAX_FILE_SIZE_MB)
    if not ok:
        os.remove(file_path)
        await message.answer(msg)
        return

    await save_upload(
        settings.DATABASE_PATH,
        user_id=user_id,
        file_path=file_path,
        original_name=doc.file_name,
    )
    log.info(f"Upload saved: {file_path}")
    await message.answer(
        f"✅ Файл <b>{doc.file_name}</b> успешно загружен!\n"
        "Используйте /report для получения отчёта.",
        parse_mode="HTML",
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Clear any active FSM state."""
    current = await state.get_state()
    await state.clear()
    if current:
        await message.answer("❌ Действие отменено.")
    else:
        await message.answer("Нечего отменять.")


# ── /history ─────────────────────────────────────────────────────────────────

@router.message(Command("history"))
@router.message(F.text == "📋 История")
async def cmd_history(message: Message) -> None:
    """Show last 10 reports with replay buttons."""
    user_id = message.from_user.id
    logger.bind(user_id=user_id).info("/history")
    reports = await get_user_reports(
        settings.DATABASE_PATH, user_id, limit=settings.MAX_HISTORY_ITEMS
    )

    if not reports:
        await message.answer("📭 История отчётов пуста. Загрузите файл через /upload.")
        return

    await message.answer(
        f"📋 <b>Последние {len(reports)} отчётов:</b>", parse_mode="HTML"
    )
    for r in reports:
        rev = f"{r['revenue']:,.0f}".replace(",", "\u00a0")
        text = (
            f"📅 {r['created_at'][:16]}\n"
            f"📁 {r['file_name']}\n"
            f"💰 {rev}\u00a0₽ · {r['positions']} поз."
        )
        await message.answer(text, reply_markup=history_inline_kb(r["id"]))


@router.callback_query(F.data.startswith("history:show:"))
async def cb_history_show(callback: CallbackQuery) -> None:
    """Replay a historical report from summary_json."""
    await callback.answer()
    report_id = int(callback.data.split(":")[-1])
    report = await get_report_by_id(settings.DATABASE_PATH, report_id)
    if not report:
        await callback.message.answer("❌ Отчёт не найден.")
        return

    summary = json.loads(report["summary_json"])
    result = ParseResult(
        file_name=report["file_name"],
        revenue=report["revenue"],
        positions=report["positions"],
        avg_check=report["avg_check"],
        top_products=summary.get("top_products", []),
        top_categories=summary.get("top_categories", []),
        low_stock=summary.get("low_stock", []),
        zero_stock=summary.get("zero_stock", []),
        date_from=None,
        date_to=None,
        period_days=summary.get("period_days"),
    )
    await callback.message.answer(
        format_brief(result), reply_markup=report_inline_kb(), parse_mode="HTML"
    )


# ── /settings ────────────────────────────────────────────────────────────────

@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: Message) -> None:
    """Show settings inline menu."""
    user = await get_user(settings.DATABASE_PATH, message.from_user.id)
    if not user:
        await message.answer("Сначала выполните /start")
        return
    await message.answer(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_inline_kb(
            user["report_mode"],
            user["report_time"],
            user["timezone"],
            user["scheduler_enabled"],
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "settings:mode")
async def cb_settings_mode(callback: CallbackQuery) -> None:
    """Open report mode selection."""
    await callback.answer()
    await callback.message.edit_text(
        "📋 Выберите режим отчёта:", reply_markup=report_mode_kb()
    )


@router.callback_query(F.data.startswith("mode:"))
async def cb_mode_selected(callback: CallbackQuery) -> None:
    """Save selected report mode."""
    mode = callback.data.split(":")[1]
    await update_user_settings(settings.DATABASE_PATH, callback.from_user.id, report_mode=mode)
    await callback.answer(f"Режим изменён: {mode}")
    user = await get_user(settings.DATABASE_PATH, callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_inline_kb(
            user["report_mode"], user["report_time"], user["timezone"], user["scheduler_enabled"]
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "settings:time")
async def cb_settings_time(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt user to enter new report time."""
    await callback.answer()
    await state.set_state(SettingsStates.waiting_for_time)
    await callback.message.answer(
        "🕐 Введите время авторассылки в формате <b>HH:MM</b>\n"
        "Например: <code>09:00</code> или <code>18:30</code>\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="HTML",
    )


@router.message(SettingsStates.waiting_for_time)
async def handle_time_input(message: Message, state: FSMContext, bot: Bot) -> None:
    """Validate and save new report time, reschedule job."""
    import re
    text = message.text.strip() if message.text else ""
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", text):
        await message.answer(
            "❌ Неверный формат. Введите время как <b>HH:MM</b>, например <code>09:00</code>.",
            parse_mode="HTML",
        )
        return

    await state.clear()
    user_id = message.from_user.id
    await update_user_settings(settings.DATABASE_PATH, user_id, report_time=text)

    # Reschedule job with new time
    from excel_report_bot.main import scheduler
    from excel_report_bot.scheduler.jobs import register_user_job
    user = await get_user(settings.DATABASE_PATH, user_id)
    if user["scheduler_enabled"]:
        register_user_job(scheduler, bot, user)

    await message.answer(
        f"✅ Время авторассылки изменено на <b>{text}</b>",
        parse_mode="HTML",
    )
    await message.answer(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_inline_kb(
            user["report_mode"], user["report_time"], user["timezone"], user["scheduler_enabled"]
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "settings:tz")
async def cb_settings_tz(callback: CallbackQuery) -> None:
    """Open timezone selection."""
    await callback.answer()
    await callback.message.edit_text(
        "🌍 Выберите часовой пояс:", reply_markup=timezone_kb()
    )


@router.callback_query(F.data.startswith("tz:"))
async def cb_tz_selected(callback: CallbackQuery) -> None:
    """Save selected timezone."""
    tz = callback.data[3:]
    await update_user_settings(settings.DATABASE_PATH, callback.from_user.id, timezone=tz)
    await callback.answer(f"Часовой пояс: {tz}")
    user = await get_user(settings.DATABASE_PATH, callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_inline_kb(
            user["report_mode"], user["report_time"], user["timezone"], user["scheduler_enabled"]
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "settings:toggle_scheduler")
async def cb_toggle_scheduler(callback: CallbackQuery, bot: Bot) -> None:
    """Toggle auto-report scheduler on/off and reschedule job."""
    user = await get_user(settings.DATABASE_PATH, callback.from_user.id)
    new_val = 0 if user["scheduler_enabled"] else 1
    await update_user_settings(
        settings.DATABASE_PATH, callback.from_user.id, scheduler_enabled=new_val
    )

    from excel_report_bot.main import scheduler
    from excel_report_bot.scheduler.jobs import register_user_job

    job_id = f"report_{callback.from_user.id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if new_val:
        updated = await get_user(settings.DATABASE_PATH, callback.from_user.id)
        register_user_job(scheduler, bot, updated)

    await callback.answer("Авторассылка " + ("включена ✅" if new_val else "выключена ❌"))
    user = await get_user(settings.DATABASE_PATH, callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_inline_kb(
            user["report_mode"], user["report_time"], user["timezone"], user["scheduler_enabled"]
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "settings:back")
async def cb_settings_back(callback: CallbackQuery) -> None:
    """Return to main settings menu."""
    await callback.answer()
    user = await get_user(settings.DATABASE_PATH, callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_inline_kb(
            user["report_mode"], user["report_time"], user["timezone"], user["scheduler_enabled"]
        ),
        parse_mode="HTML",
    )


# ── /help ────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message) -> None:
    """Show all available commands with descriptions."""
    logger.bind(user_id=message.from_user.id).info("/help")
    await message.answer(
        "📖 <b>Доступные команды</b>\n\n"
        "📊 <b>Отчёты</b>\n"
        "/report — отчёт по последнему файлу\n"
        "/compare — сравнение двух последних периодов\n"
        "/history — последние 10 отчётов\n"
        "/export — скачать отчёт как .txt файл\n\n"
        "📤 <b>Загрузка</b>\n"
        "/upload — загрузить .xlsx файл (до 10 МБ)\n\n"
        "⚙️ <b>Настройки</b>\n"
        "/settings — режим отчёта, время и часовой пояс авторассылки\n\n"
        "🔧 <b>Прочее</b>\n"
        "/start — главное меню\n"
        "/cancel — отмена текущего действия\n\n"
        "📋 <b>Режимы отчёта</b>\n"
        "• <b>Кратко</b> — выручка, позиции, топ-3, остатки\n"
        "• <b>Полный</b> — топ-5 товаров, категории, остатки, ABC-анализ\n"
        "• <b>С графиком</b> — полный отчёт + 2 графика (топ и динамика по дням)\n\n"
        "📌 <b>Формат Excel</b>\n"
        "Колонки: Товар, Количество, Сумма, Остаток, Категория, Дата\n"
        "(регистр и порядок не важны, поддерживаются русские и английские названия)",
        parse_mode="HTML",
    )


# ── /export ───────────────────────────────────────────────────────────────────

@router.message(Command("export"))
@router.message(F.text == "📄 Экспорт")
async def cmd_export(message: Message) -> None:
    """Export last report as a plain .txt file."""
    user_id = message.from_user.id
    logger.bind(user_id=user_id).info("/export")

    uploads = await get_latest_uploads(settings.DATABASE_PATH, user_id, limit=1)
    if not uploads:
        await message.answer("⚠️ Файл не загружен. Используйте /upload.")
        return

    upload = uploads[0]
    if not os.path.exists(upload["file_path"]):
        await message.answer("❌ Файл не найден на сервере. Загрузите файл заново.")
        return

    try:
        result = parse_excel(upload["file_path"], upload["original_name"])
    except Exception as e:
        logger.bind(user_id=user_id).error(f"Export parse error: {e}")
        await message.answer(f"❌ Ошибка при разборе файла:\n<code>{e}</code>", parse_mode="HTML")
        return

    plain_text = format_export(result)
    filename = upload["original_name"].replace(".xlsx", "") + "_report.txt"
    await message.answer_document(
        BufferedInputFile(plain_text.encode("utf-8"), filename=filename),
        caption="📄 Полный отчёт в текстовом формате",
    )


# ── /compare ─────────────────────────────────────────────────────────────────

@router.message(Command("compare"))
@router.message(F.text == "📈 Сравнить")
async def cmd_compare(message: Message) -> None:
    """Compare the two most recently uploaded files."""
    user_id = message.from_user.id
    logger.bind(user_id=user_id).info("/compare")
    uploads = await get_latest_uploads(settings.DATABASE_PATH, user_id, limit=2)
    if len(uploads) < 2:
        await message.answer(
            "⚠️ Для сравнения нужно минимум два загруженных файла.\n"
            "Загрузите ещё один файл через /upload."
        )
        return

    # uploads[0] is newest, uploads[1] is older
    newer, older = uploads[0], uploads[1]
    for u in [older, newer]:
        if not os.path.exists(u["file_path"]):
            await message.answer(f"❌ Файл {u['original_name']} не найден на сервере.")
            return

    try:
        r1 = parse_excel(uploads[0]["file_path"], uploads[0]["original_name"])
        r2 = parse_excel(uploads[1]["file_path"], uploads[1]["original_name"])
    except Exception as e:
        logger.bind(user_id=user_id).error(f"Compare parse error: {e}")
        await message.answer(
            f"❌ Ошибка при разборе файлов:\n<code>{e}</code>", parse_mode="HTML"
        )
        return

    # Sort by date_from so Период 1 is always the earlier period
    if r1.date_from and r2.date_from and r1.date_from > r2.date_from:
        r1, r2 = r2, r1

    await message.answer(format_compare(r1, r2), parse_mode="HTML")
