"""Generate matplotlib bar charts for report data."""
import asyncio
from io import BytesIO
from functools import partial

from excel_report_bot.parser.excel_parser import ParseResult

# Dark theme colors (Catppuccin Mocha)
BG_COLOR = "#1e1e2e"
TEXT_COLOR = "#cdd6f4"
BAR_COLORS = ["#89b4fa", "#74c7ec", "#89dceb", "#a6e3a1", "#313244"]


def _render_chart(result: ParseResult) -> BytesIO:
    """Synchronous chart rendering — run in executor to avoid blocking event loop."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    products = result.top_products[:5]
    names = [p["name"] for p in products]
    revenues = [p["revenue"] for p in products]

    # Reverse so highest revenue bar is at top
    names = names[::-1]
    revenues = revenues[::-1]
    colors = (BAR_COLORS[:len(names)])[::-1]

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    bars = ax.barh(names, revenues, color=colors, height=0.6)

    # Value labels inside bars
    for bar, rev in zip(bars, revenues):
        ax.text(
            bar.get_width() * 0.98,
            bar.get_y() + bar.get_height() / 2,
            f"{rev:,.0f} ₽",
            va="center",
            ha="right",
            color=TEXT_COLOR,
            fontsize=10,
            fontweight="bold",
        )

    ax.tick_params(colors=TEXT_COLOR, labelsize=10)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.xaxis.set_visible(False)
    ax.yaxis.label.set_color(TEXT_COLOR)
    for label in ax.get_yticklabels():
        label.set_color(TEXT_COLOR)

    title = "ТОП товаров по выручке"
    if result.date_from and result.date_to:
        d_from = result.date_from[8:10] + "." + result.date_from[5:7]
        d_to = result.date_to[8:10] + "." + result.date_to[5:7]
        title += f" ({d_from}–{d_to})"
    ax.set_title(title, color=TEXT_COLOR, fontsize=13, pad=12)

    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=120, facecolor=BG_COLOR)
    plt.close(fig)
    buf.seek(0)
    return buf


async def generate_top_chart(result: ParseResult) -> BytesIO:
    """Generate top-products bar chart; returns PNG as BytesIO."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_render_chart, result))


def _render_daily_chart(result: ParseResult) -> BytesIO:
    """Synchronous daily revenue bar chart — run in executor."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import date as date_type

    daily = result.daily_revenue  # [{"date": "YYYY-MM-DD", "revenue": float}]
    dates = [date_type.fromisoformat(d["date"]) for d in daily]
    revenues = [d["revenue"] for d in daily]

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    # Bar width depends on total days — keep them tight
    bar_w = 0.7 if len(dates) > 14 else 0.5

    ax.bar(dates, revenues, color="#89b4fa", width=bar_w, linewidth=0)

    # Annotate only if few bars (≤ 15) to avoid clutter
    if len(dates) <= 15:
        for d, r in zip(dates, revenues):
            ax.text(
                d, r + max(revenues) * 0.01,
                f"{r / 1000:.0f}к" if r >= 1000 else f"{r:.0f}",
                ha="center", va="bottom",
                color=TEXT_COLOR, fontsize=8,
            )

    # X-axis: format dates nicely
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    if len(dates) > 20:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator())
    fig.autofmt_xdate(rotation=45)

    ax.tick_params(colors=TEXT_COLOR, labelsize=9)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.yaxis.set_visible(False)
    for label in ax.get_xticklabels():
        label.set_color(TEXT_COLOR)

    title = "Выручка по дням"
    if result.date_from and result.date_to:
        d_from = result.date_from[8:10] + "." + result.date_from[5:7]
        d_to = result.date_to[8:10] + "." + result.date_to[5:7]
        title += f" ({d_from}–{d_to})"
    ax.set_title(title, color=TEXT_COLOR, fontsize=13, pad=12)

    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=120, facecolor=BG_COLOR)
    plt.close(fig)
    buf.seek(0)
    return buf


async def generate_daily_chart(result: ParseResult) -> BytesIO | None:
    """Generate daily revenue bar chart. Returns None if no daily data."""
    if not result.daily_revenue or len(result.daily_revenue) < 2:
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_render_daily_chart, result))
