import pytest
from excel_report_bot.parser.excel_parser import ParseResult


def make_result(**kwargs) -> ParseResult:
    defaults = dict(
        file_name="test.xlsx",
        revenue=1234567.0,
        positions=342,
        avg_check=3610.0,
        top_products=[
            {"name": "Товар А", "revenue": 234500.0, "share_pct": 19.0},
            {"name": "Товар Б", "revenue": 187200.0, "share_pct": 15.0},
            {"name": "Товар В", "revenue": 143800.0, "share_pct": 12.0},
        ],
        top_categories=[{"name": "Еда", "revenue": 800000.0}],
        low_stock=["Товар Х", "Товар У", "Товар З"],
        zero_stock=["Товар М", "Товар Н"],
        date_from="2026-04-01",
        date_to="2026-04-05",
        period_days=5,
    )
    defaults.update(kwargs)
    return ParseResult(**defaults)


def test_format_brief_contains_revenue():
    """format_brief includes formatted revenue."""
    from excel_report_bot.utils.formatters import format_brief
    text = format_brief(make_result())
    assert "1" in text and "234" in text and "567" in text


def test_format_brief_contains_top_product():
    """format_brief includes top product name."""
    from excel_report_bot.utils.formatters import format_brief
    text = format_brief(make_result())
    assert "Товар А" in text


def test_format_brief_contains_low_stock():
    """format_brief mentions low stock products."""
    from excel_report_bot.utils.formatters import format_brief
    text = format_brief(make_result())
    assert "Товар Х" in text


def test_format_brief_contains_zero_stock():
    """format_brief mentions zero stock products."""
    from excel_report_bot.utils.formatters import format_brief
    text = format_brief(make_result())
    assert "Товар М" in text


def test_format_full_returns_list_of_strings():
    """format_full returns list of str, each ≤ 4096 chars."""
    from excel_report_bot.utils.formatters import format_full
    parts = format_full(make_result())
    assert isinstance(parts, list)
    assert all(isinstance(p, str) for p in parts)
    assert all(len(p) <= 4096 for p in parts)


def test_format_compare_shows_delta():
    """format_compare shows ▲ or ▼ symbol."""
    from excel_report_bot.utils.formatters import format_compare
    r1 = make_result(revenue=1000.0, date_from="2026-03-01", date_to="2026-03-31")
    r2 = make_result(revenue=1200.0, date_from="2026-04-01", date_to="2026-04-30")
    text = format_compare(r1, r2)
    assert "▲" in text or "▼" in text


def test_format_compare_shows_period():
    """format_compare displays date ranges for both periods."""
    from excel_report_bot.utils.formatters import format_compare
    r1 = make_result(revenue=1000.0, date_from="2026-03-01", date_to="2026-03-31")
    r2 = make_result(revenue=1200.0, date_from="2026-04-01", date_to="2026-04-30")
    text = format_compare(r1, r2)
    assert "01.03" in text
    assert "01.04" in text


def test_format_compare_shows_daily_revenue():
    """format_compare includes per-day revenue when period_days is set."""
    from excel_report_bot.utils.formatters import format_compare
    r1 = make_result(revenue=3000.0, period_days=3, date_from="2026-03-01", date_to="2026-03-03")
    r2 = make_result(revenue=6000.0, period_days=3, date_from="2026-04-01", date_to="2026-04-03")
    text = format_compare(r1, r2)
    assert "день" in text
    # r2 daily = 2000, r1 daily = 1000 → +100% growth
    assert "▲" in text


def test_format_compare_shows_common_categories():
    """format_compare includes category comparison for shared categories."""
    from excel_report_bot.utils.formatters import format_compare
    r1 = make_result(
        revenue=1000.0,
        top_categories=[{"name": "Еда", "revenue": 600.0}, {"name": "Напитки", "revenue": 400.0}],
    )
    r2 = make_result(
        revenue=1200.0,
        top_categories=[{"name": "Еда", "revenue": 700.0}, {"name": "Напитки", "revenue": 500.0}],
    )
    text = format_compare(r1, r2)
    assert "Еда" in text
    assert "Напитки" in text


def test_format_full_contains_abc():
    """format_full includes ABC analysis section when abc_analysis is non-empty."""
    from excel_report_bot.utils.formatters import format_full
    result = make_result(abc_analysis={"A": ["Товар А", "Товар Б"], "B": ["Товар В"], "C": ["Товар Г"]})
    combined = "\n".join(format_full(result))
    assert "ABC" in combined
    assert "Класс A" in combined
    assert "Товар А" in combined


def test_format_export_no_html_tags():
    """format_export returns plain text without HTML tags."""
    from excel_report_bot.utils.formatters import format_export
    result = make_result(abc_analysis={"A": ["Товар А"], "B": [], "C": []})
    text = format_export(result)
    assert "<b>" not in text
    assert "<code>" not in text
    assert "</b>" not in text
    assert "Выручка" in text  # content still present
