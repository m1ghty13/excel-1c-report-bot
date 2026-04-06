import pytest


def test_settings_loads_from_env(monkeypatch):
    """Settings object reads all required fields from environment."""
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("ADMIN_IDS", "111,222")
    monkeypatch.setenv("ALLOWED_USERS", "111,222,333")

    from excel_report_bot.config import Settings
    s = Settings()
    assert s.BOT_TOKEN == "123:ABC"
    assert s.admin_ids == [111, 222]
    assert s.allowed_users == [111, 222, 333]
    assert s.REPORT_TIME == "09:00"
    assert s.TIMEZONE == "Europe/Moscow"
    assert s.MAX_FILE_SIZE_MB == 10
    assert s.DATABASE_PATH == "data/reports.db"
    assert s.HEALTH_PORT == 8080


def test_admin_ids_parsed_with_spaces(monkeypatch):
    """ADMIN_IDS with spaces around commas parses correctly."""
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("ADMIN_IDS", " 111 , 222 ")
    monkeypatch.setenv("ALLOWED_USERS", "111")
    from excel_report_bot.config import Settings
    s = Settings()
    assert s.admin_ids == [111, 222]
