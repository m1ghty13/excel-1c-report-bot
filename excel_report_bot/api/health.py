"""FastAPI health check endpoint."""
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from excel_report_bot.config import settings
from excel_report_bot.db.database import get_stats

app = FastAPI(title="Excel Report Bot Health", docs_url=None, redoc_url=None)

# Set by main.py on_startup via set_start_time()
_start_time: datetime = datetime.now(timezone.utc)


def set_start_time(dt: datetime) -> None:
    """Store bot start time for uptime calculation."""
    global _start_time
    _start_time = dt


def _format_uptime(start: datetime) -> str:
    """Format uptime as '2d 4h 13m'."""
    delta = datetime.now(timezone.utc) - start
    total_seconds = int(delta.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


@app.get("/health")
async def health() -> JSONResponse:
    """Return bot health status and key metrics."""
    stats = await get_stats(settings.DATABASE_PATH)
    return JSONResponse({
        "status": "ok",
        "uptime": _format_uptime(_start_time),
        "last_report": stats.get("last_report") or "never",
        "users_total": stats["users_total"],
        "reports_today": stats["reports_today"],
    })
