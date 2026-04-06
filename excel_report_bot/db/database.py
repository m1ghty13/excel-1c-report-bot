"""All database operations — raw aiosqlite, no ORM."""
import json
import os
import aiosqlite
from datetime import datetime, timedelta
from typing import Any


_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id           INTEGER PRIMARY KEY,
    username          TEXT,
    role              TEXT DEFAULT 'viewer',
    report_mode       TEXT DEFAULT 'brief',
    report_time       TEXT DEFAULT '09:00',
    timezone          TEXT DEFAULT 'Europe/Moscow',
    scheduler_enabled INTEGER DEFAULT 1,
    created_at        TEXT DEFAULT (datetime('now'))
)
"""

_CREATE_REPORTS = """
CREATE TABLE IF NOT EXISTS reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER,
    file_name    TEXT,
    revenue      REAL,
    positions    INTEGER,
    avg_check    REAL,
    created_at   TEXT DEFAULT (datetime('now')),
    summary_json TEXT
)
"""

_CREATE_UPLOADS = """
CREATE TABLE IF NOT EXISTS uploads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER,
    file_path     TEXT,
    original_name TEXT,
    uploaded_at   TEXT DEFAULT (datetime('now'))
)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_reports_user_id ON reports(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_user_id ON uploads(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_uploads_user_uploaded ON uploads(user_id, uploaded_at DESC)",
]


async def init_db(db_path: str) -> None:
    """Create all tables and indexes if they don't exist."""
    dir_name = os.path.dirname(db_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_CREATE_USERS)
        await db.execute(_CREATE_REPORTS)
        await db.execute(_CREATE_UPLOADS)
        for idx in _INDEXES:
            await db.execute(idx)
        await db.commit()


async def upsert_user(
    db_path: str,
    user_id: int,
    username: str | None,
    role: str = "viewer",
) -> None:
    """Insert or update user record, preserving existing settings."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, role)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
            """,
            (user_id, username, role),
        )
        await db.commit()


async def get_user(db_path: str, user_id: int) -> dict[str, Any] | None:
    """Return user row as dict or None if not found."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_users(db_path: str) -> list[dict[str, Any]]:
    """Return all users ordered by creation date descending."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
            return [dict(row) async for row in cursor]


async def get_scheduled_users(db_path: str) -> list[dict[str, Any]]:
    """Return users with scheduler_enabled = 1."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE scheduler_enabled = 1"
        ) as cursor:
            return [dict(row) async for row in cursor]


async def update_user_settings(
    db_path: str,
    user_id: int,
    **kwargs: Any,
) -> None:
    """Update arbitrary user settings columns."""
    if not kwargs:
        return
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"UPDATE users SET {cols} WHERE user_id = ?", values
        )
        await db.commit()


async def save_report(
    db_path: str,
    user_id: int,
    file_name: str,
    revenue: float,
    positions: int,
    avg_check: float,
    summary: dict,
) -> int:
    """Save report and return its id."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO reports (user_id, file_name, revenue, positions, avg_check, summary_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, file_name, revenue, positions, avg_check,
             json.dumps(summary, ensure_ascii=False)),
        )
        await db.commit()
        return cursor.lastrowid


async def get_user_reports(
    db_path: str, user_id: int, limit: int = 10
) -> list[dict[str, Any]]:
    """Return last N reports for user, most recent first."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM reports WHERE user_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (user_id, limit),
        ) as cursor:
            return [dict(row) async for row in cursor]


async def get_report_by_id(db_path: str, report_id: int) -> dict[str, Any] | None:
    """Return single report by id."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reports WHERE id = ?", (report_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def save_upload(
    db_path: str, user_id: int, file_path: str, original_name: str
) -> int:
    """Save upload record and return its id."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "INSERT INTO uploads (user_id, file_path, original_name) VALUES (?, ?, ?)",
            (user_id, file_path, original_name),
        )
        await db.commit()
        return cursor.lastrowid


async def get_latest_uploads(
    db_path: str, user_id: int, limit: int = 2
) -> list[dict[str, Any]]:
    """Return last N uploads for user, most recent first."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM uploads WHERE user_id = ?
            ORDER BY uploaded_at DESC, id DESC LIMIT ?
            """,
            (user_id, limit),
        ) as cursor:
            return [dict(row) async for row in cursor]


async def get_stats(db_path: str) -> dict[str, Any]:
    """Return bot-wide statistics for /stats command and /health endpoint."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            users_total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM reports") as c:
            reports_total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM uploads") as c:
            uploads_total = (await c.fetchone())[0]
        async with db.execute("SELECT MAX(created_at) FROM reports") as c:
            last_report = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM reports WHERE created_at >= date('now')"
        ) as c:
            reports_today = (await c.fetchone())[0]
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT u.user_id, u.username, COUNT(r.id) as report_count
            FROM users u LEFT JOIN reports r ON u.user_id = r.user_id
            GROUP BY u.user_id ORDER BY report_count DESC LIMIT 5
            """
        ) as cursor:
            top_users = [dict(row) async for row in cursor]
    return {
        "users_total": users_total,
        "reports_total": reports_total,
        "uploads_total": uploads_total,
        "last_report": last_report,
        "reports_today": reports_today,
        "top_users": top_users,
    }


async def delete_old_uploads(db_path: str, days: int = 30) -> list[str]:
    """Delete uploads older than `days`, return list of file paths removed."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT file_path FROM uploads WHERE uploaded_at < ?", (cutoff,)
        ) as cursor:
            paths = [row[0] async for row in cursor]
        await db.execute("DELETE FROM uploads WHERE uploaded_at < ?", (cutoff,))
        await db.commit()
    return paths
