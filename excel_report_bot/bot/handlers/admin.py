"""Admin command handlers: /stats /broadcast /users."""
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from loguru import logger

from excel_report_bot.bot.filters import IsAdmin
from excel_report_bot.bot.keyboards import broadcast_confirm_kb
from excel_report_bot.config import settings
from excel_report_bot.db.database import get_all_users, get_stats

router = Router()
router.message.filter(IsAdmin())


class BroadcastStates(StatesGroup):
    """FSM states for /broadcast flow."""
    waiting_for_message = State()


# ── /stats ───────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Show bot-wide usage statistics."""
    logger.bind(user_id=message.from_user.id).info("/stats")
    s = await get_stats(settings.DATABASE_PATH)

    top_users_text = "\n".join(
        f"  {i+1}. @{u['username'] or u['user_id']} — {u['report_count']} отч."
        for i, u in enumerate(s["top_users"])
    ) or "  нет данных"

    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{s['users_total']}</b>\n"
        f"📋 Отчётов всего: <b>{s['reports_total']}</b>\n"
        f"📋 Сегодня: <b>{s['reports_today']}</b>\n"
        f"📤 Загрузок: <b>{s['uploads_total']}</b>\n"
        f"🕐 Последний отчёт: <b>{s['last_report'] or '—'}</b>\n\n"
        f"🏆 Топ пользователи:\n{top_users_text}",
        parse_mode="HTML",
    )


# ── /users ───────────────────────────────────────────────────────────────────

@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    """List all registered users."""
    logger.bind(user_id=message.from_user.id).info("/users")
    users = await get_all_users(settings.DATABASE_PATH)
    if not users:
        await message.answer("Нет зарегистрированных пользователей.")
        return

    lines = ["👥 <b>Пользователи:</b>\n"]
    for u in users:
        role_icon = "👑" if u["role"] == "admin" else "👤"
        name = f"@{u['username']}" if u["username"] else str(u["user_id"])
        lines.append(
            f"{role_icon} {name} (<code>{u['user_id']}</code>) — {u['created_at'][:10]}"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ── /broadcast ───────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    """Initiate broadcast — next message will be sent to all users."""
    await state.set_state(BroadcastStates.waiting_for_message)
    logger.bind(user_id=message.from_user.id).info("/broadcast initiated")
    users = await get_all_users(settings.DATABASE_PATH)
    await message.answer(
        f"📢 Следующее сообщение будет разослано <b>{len(users)}</b> пользователям.\n"
        "Напишите сообщение для рассылки или отправьте /cancel для отмены.",
        parse_mode="HTML",
    )


@router.message(BroadcastStates.waiting_for_message)
async def handle_broadcast_message(message: Message, state: FSMContext) -> None:
    """Preview broadcast message and ask for confirmation."""
    await state.update_data(broadcast_text=message.text)
    users = await get_all_users(settings.DATABASE_PATH)
    await message.answer(
        f"📋 <b>Предпросмотр рассылки:</b>\n\n{message.text}\n\n"
        f"Разослать {len(users)} пользователям?",
        reply_markup=broadcast_confirm_kb(len(users)),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "broadcast:confirm")
async def cb_broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Execute broadcast to all users."""
    data = await state.get_data()
    await state.clear()
    text = data.get("broadcast_text", "")
    users = await get_all_users(settings.DATABASE_PATH)

    await callback.answer("Рассылка началась...")
    await callback.message.edit_reply_markup(reply_markup=None)

    sent = 0
    failed = 0
    for user in users:
        try:
            await bot.send_message(user["user_id"], text)
            sent += 1
        except Exception as e:
            logger.warning(f"Broadcast failed for {user['user_id']}: {e}")
            failed += 1

    logger.bind(user_id=callback.from_user.id).info(
        f"Broadcast complete: sent={sent}, failed={failed}"
    )
    await callback.message.answer(
        f"✅ Рассылка завершена: отправлено {sent}, ошибок {failed}."
    )


@router.callback_query(F.data == "broadcast:cancel")
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel broadcast."""
    await state.clear()
    await callback.answer("Рассылка отменена.")
    await callback.message.edit_reply_markup(reply_markup=None)
