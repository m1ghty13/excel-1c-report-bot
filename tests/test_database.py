import pytest
import json


@pytest.fixture
def tmp_db(tmp_path):
    """Temporary SQLite database path."""
    return str(tmp_path / "test.db")


async def test_init_db_creates_tables(tmp_db):
    """init_db creates all three tables and indexes."""
    from excel_report_bot.db.database import init_db
    await init_db(tmp_db)
    import aiosqlite
    async with aiosqlite.connect(tmp_db) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            tables = {row[0] async for row in cursor}
    assert "users" in tables
    assert "reports" in tables
    assert "uploads" in tables


async def test_upsert_user(tmp_db):
    """upsert_user inserts then updates without error."""
    from excel_report_bot.db.database import init_db, upsert_user, get_user
    await init_db(tmp_db)
    await upsert_user(tmp_db, user_id=111, username="alice", role="viewer")
    user = await get_user(tmp_db, 111)
    assert user["username"] == "alice"
    assert user["role"] == "viewer"
    await upsert_user(tmp_db, user_id=111, username="alice2", role="admin")
    user = await get_user(tmp_db, 111)
    assert user["username"] == "alice2"


async def test_save_and_get_report(tmp_db):
    """save_report stores report; get_user_reports retrieves it."""
    from excel_report_bot.db.database import init_db, upsert_user, save_report, get_user_reports
    await init_db(tmp_db)
    await upsert_user(tmp_db, user_id=111, username="alice", role="viewer")
    summary = {
        "top_products": [{"name": "A", "revenue": 100.0, "share_pct": 50.0}],
        "low_stock": [],
        "zero_stock": [],
        "top_categories": [],
        "period_days": 30,
    }
    await save_report(tmp_db, user_id=111, file_name="test.xlsx",
                      revenue=1000.0, positions=10, avg_check=100.0,
                      summary=summary)
    reports = await get_user_reports(tmp_db, 111, limit=10)
    assert len(reports) == 1
    assert reports[0]["revenue"] == 1000.0
    assert json.loads(reports[0]["summary_json"])["period_days"] == 30


async def test_save_and_get_upload(tmp_db):
    """save_upload and get_latest_uploads work correctly."""
    from excel_report_bot.db.database import init_db, upsert_user, save_upload, get_latest_uploads
    await init_db(tmp_db)
    await upsert_user(tmp_db, user_id=111, username="u", role="viewer")
    await save_upload(tmp_db, user_id=111, file_path="uploads/111_1_a.xlsx",
                      original_name="a.xlsx")
    await save_upload(tmp_db, user_id=111, file_path="uploads/111_2_b.xlsx",
                      original_name="b.xlsx")
    uploads = await get_latest_uploads(tmp_db, 111, limit=2)
    assert len(uploads) == 2
    assert uploads[0]["original_name"] == "b.xlsx"
