"""Format ParseResult objects into Telegram-ready text."""
import re
from excel_report_bot.parser.excel_parser import ParseResult

_MAX_MSG = 4096


def _fmt_money(amount: float) -> str:
    """Format float as Russian money string: 1 234 567 ₽"""
    # Format with space as thousands separator
    formatted = f"{amount:,.0f}".replace(",", "\u00a0")
    return formatted + "\u00a0₽"


def _fmt_date(iso: str | None) -> str:
    """Convert 'YYYY-MM-DD' to 'DD.MM.YYYY'."""
    if not iso:
        return "?"
    parts = iso.split("-")
    return f"{parts[2]}.{parts[1]}.{parts[0]}"


def _split_text(text: str) -> list[str]:
    """Split text into chunks ≤ 4096 chars, splitting on newline boundaries."""
    if len(text) <= _MAX_MSG:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1  # +1 for \n
        if current_len + line_len > _MAX_MSG and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def format_brief(result: ParseResult) -> str:
    """Format a one-message summary of ParseResult."""
    date_label = (
        f"{_fmt_date(result.date_from)}–{_fmt_date(result.date_to)}"
        if result.date_from
        else result.file_name
    )

    top_lines = "\n".join(
        f"  {i+1}. {p['name']} — {_fmt_money(p['revenue'])} ({p['share_pct']:.0f}%)"
        for i, p in enumerate(result.top_products[:3])
    )

    low = ", ".join(result.low_stock) if result.low_stock else "—"
    zero = ", ".join(result.zero_stock) if result.zero_stock else "—"
    low_count = len(result.low_stock)
    zero_count = len(result.zero_stock)

    return (
        f"📊 <b>Отчёт за {date_label}</b>\n\n"
        f"💰 Выручка: <b>{_fmt_money(result.revenue)}</b>\n"
        f"📦 Позиций: <b>{result.positions}</b>\n"
        f"🧾 Средний чек: <b>{_fmt_money(result.avg_check)}</b>\n\n"
        f"🏆 <b>ТОП товары:</b>\n{top_lines}\n\n"
        f"⚠️ Заканчивается ({low_count} поз.): {low}\n"
        f"🚫 Нет в наличии ({zero_count} поз.): {zero}"
    )


def format_full(result: ParseResult) -> list[str]:
    """Format a multi-message detailed report. Each message ≤ 4096 chars."""
    date_label = (
        f"{_fmt_date(result.date_from)}–{_fmt_date(result.date_to)}"
        if result.date_from
        else result.file_name
    )

    part1 = (
        f"📊 <b>Полный отчёт за {date_label}</b>\n\n"
        f"💰 Выручка: <b>{_fmt_money(result.revenue)}</b>\n"
        f"📦 Позиций: <b>{result.positions}</b>\n"
        f"🧾 Средний чек: <b>{_fmt_money(result.avg_check)}</b>"
    )

    top_lines = "\n".join(
        f"  {i+1}. {p['name']}\n"
        f"     {_fmt_money(p['revenue'])} · {p['share_pct']:.1f}% от выручки"
        for i, p in enumerate(result.top_products)
    )
    part2 = f"🏆 <b>ТОП-{len(result.top_products)} товаров по выручке:</b>\n\n{top_lines}"

    if result.top_categories:
        cat_lines = "\n".join(
            f"  {i+1}. {c['name']} — {_fmt_money(c['revenue'])}"
            for i, c in enumerate(result.top_categories)
        )
        part3 = f"📂 <b>ТОП категории:</b>\n\n{cat_lines}"
    else:
        part3 = "📂 <b>Категории:</b> данные отсутствуют"

    low_lines = "\n".join(f"  • {n}" for n in result.low_stock) or "  нет"
    zero_lines = "\n".join(f"  • {n}" for n in result.zero_stock) or "  нет"
    part4 = (
        f"⚠️ <b>Заканчивается (остаток &lt; 5 шт.):</b>\n{low_lines}\n\n"
        f"🚫 <b>Нет в наличии:</b>\n{zero_lines}"
    )

    # --- ABC analysis section ---
    abc = result.abc_analysis
    a_count = len(abc.get("A", []))
    b_count = len(abc.get("B", []))
    c_count = len(abc.get("C", []))
    if a_count + b_count + c_count > 0:
        a_names = ", ".join(abc["A"][:5]) + ("..." if a_count > 5 else "")
        b_names = ", ".join(abc["B"][:3]) + ("..." if b_count > 3 else "")
        c_names = f"{c_count} позиций"
        part5 = (
            f"🔬 <b>ABC-анализ</b>\n\n"
            f"🅐 <b>Класс A</b> ({a_count} поз.) — 80% выручки:\n  {a_names}\n\n"
            f"🅑 <b>Класс B</b> ({b_count} поз.) — след. 15%:\n  {b_names or '—'}\n\n"
            f"🅒 <b>Класс C</b> — {c_names} (оставшиеся 5%)"
        )
    else:
        part5 = None

    messages: list[str] = []
    for part in [part1, part2, part3, part4]:
        messages.extend(_split_text(part))
    if part5:
        messages.extend(_split_text(part5))
    return messages


def format_compare(r1: ParseResult, r2: ParseResult) -> str:
    """Format comparison between two ParseResult periods."""

    def period_label(r: ParseResult) -> str:
        if r.date_from and r.date_to:
            return f"{_fmt_date(r.date_from)}–{_fmt_date(r.date_to)}"
        return r.file_name

    def delta(old: float, new: float) -> str:
        if old == 0:
            return "—"
        pct = (new - old) / old * 100
        sign = "▲" if pct > 0 else "▼"
        return f"{sign} {abs(pct):.1f}%"

    p1 = period_label(r1)
    p2 = period_label(r2)

    lines = [
        f"📈 <b>Сравнение периодов</b>\n",
        f"<b>Период 1:</b> {p1}",
        f"<b>Период 2:</b> {p2}\n",
        f"💰 Выручка:",
        f"  {_fmt_money(r1.revenue)} → {_fmt_money(r2.revenue)}  {delta(r1.revenue, r2.revenue)}\n",
        f"📦 Позиций:",
        f"  {r1.positions} → {r2.positions}  {delta(r1.positions, r2.positions)}\n",
        f"🧾 Средний чек:",
        f"  {_fmt_money(r1.avg_check)} → {_fmt_money(r2.avg_check)}  {delta(r1.avg_check, r2.avg_check)}",
    ]

    # Revenue per day (only if both have period_days)
    if r1.period_days and r2.period_days:
        rpd1 = r1.revenue / r1.period_days
        rpd2 = r2.revenue / r2.period_days
        lines.append(f"\n📅 Выручка в день:")
        lines.append(
            f"  {_fmt_money(rpd1)} → {_fmt_money(rpd2)}  {delta(rpd1, rpd2)}"
        )

    # Category comparison (if both have category data)
    cats1 = {c["name"]: c["revenue"] for c in r1.top_categories}
    cats2 = {c["name"]: c["revenue"] for c in r2.top_categories}
    common_cats = [n for n in cats1 if n in cats2]
    if common_cats:
        lines.append(f"\n📂 <b>Категории:</b>")
        for name in common_cats[:3]:
            lines.append(
                f"  {name}: {_fmt_money(cats1[name])} → {_fmt_money(cats2[name])}"
                f"  {delta(cats1[name], cats2[name])}"
            )

    return "\n".join(lines)


def format_export(result: ParseResult) -> str:
    """Format full report as plain text (no HTML) for .txt file export."""
    html_text = "\n\n".join(format_full(result))
    # Strip HTML tags
    plain = re.sub(r"<[^>]+>", "", html_text)
    # Unescape &lt; &gt; &amp;
    plain = plain.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return plain
