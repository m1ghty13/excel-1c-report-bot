"""All keyboard factories for the bot."""
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Reply keyboard with all user commands."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Отчёт"), KeyboardButton(text="📤 Загрузить файл")],
            [KeyboardButton(text="📋 История"), KeyboardButton(text="📈 Сравнить")],
            [KeyboardButton(text="📄 Экспорт"), KeyboardButton(text="⚙️ Настройки")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def report_inline_kb() -> InlineKeyboardMarkup:
    """Inline keyboard shown under each report message."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="report:refresh"),
                InlineKeyboardButton(text="📥 Скачать xlsx", callback_data="report:download"),
            ]
        ]
    )


def settings_inline_kb(
    report_mode: str,
    report_time: str,
    timezone: str,
    scheduler_enabled: int,
) -> InlineKeyboardMarkup:
    """Inline keyboard for /settings — shows current values on buttons."""
    mode_label = {
        "brief": "Кратко ✓",
        "full": "Полный ✓",
        "chart": "С графиком ✓",
    }.get(report_mode, report_mode)
    sched_label = "Авторассылка: ВКЛ ✓" if scheduler_enabled else "Авторассылка: ВЫКЛ"

    builder = InlineKeyboardBuilder()
    builder.button(text=f"📋 Режим: {mode_label}", callback_data="settings:mode")
    builder.button(text=f"🕐 Время: {report_time}", callback_data="settings:time")
    builder.button(text=f"🌍 Часовой пояс: {timezone}", callback_data="settings:tz")
    builder.button(text=sched_label, callback_data="settings:toggle_scheduler")
    builder.adjust(1)
    return builder.as_markup()


def report_mode_kb() -> InlineKeyboardMarkup:
    """Inline keyboard for selecting report mode."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Кратко", callback_data="mode:brief")],
            [InlineKeyboardButton(text="📄 Полный", callback_data="mode:full")],
            [InlineKeyboardButton(text="📊 С графиком", callback_data="mode:chart")],
            [InlineKeyboardButton(text="« Назад", callback_data="settings:back")],
        ]
    )


def timezone_kb() -> InlineKeyboardMarkup:
    """Inline keyboard for selecting timezone."""
    zones = [
        ("🇷🇺 Москва (UTC+3)", "Europe/Moscow"),
        ("🇷🇺 Екатеринбург (UTC+5)", "Asia/Yekaterinburg"),
        ("🇷🇺 Новосибирск (UTC+7)", "Asia/Novosibirsk"),
        ("🇷🇺 Владивосток (UTC+10)", "Asia/Vladivostok"),
        ("🇺🇦 Киев (UTC+2/3)", "Europe/Kyiv"),
        ("🇰🇿 Алматы (UTC+5)", "Asia/Almaty"),
        ("🌍 UTC", "UTC"),
    ]
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"tz:{zone}")]
        for label, zone in zones
    ]
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="settings:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def history_inline_kb(report_id: int) -> InlineKeyboardMarkup:
    """Inline button to replay a historical report."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔁 Показать снова",
                callback_data=f"history:show:{report_id}",
            )]
        ]
    )


def broadcast_confirm_kb(count: int) -> InlineKeyboardMarkup:
    """Confirm/cancel inline keyboard for broadcast."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Разослать ({count} польз.)",
                    callback_data="broadcast:confirm",
                ),
                InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel"),
            ]
        ]
    )
