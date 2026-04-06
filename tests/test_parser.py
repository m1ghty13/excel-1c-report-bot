import pytest
import openpyxl


def make_xlsx(path: str, headers: list, rows: list) -> None:
    """Helper: write a simple xlsx file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)


# ── Validators ──────────────────────────────────────────────────────────────

def test_validate_rejects_csv(tmp_path):
    """CSV files are rejected with clear message."""
    from excel_report_bot.parser.validators import validate_file
    p = tmp_path / "data.csv"
    p.write_text("a,b,c")
    ok, msg = validate_file(str(p), max_mb=10)
    assert not ok
    assert ".xlsx" in msg


def test_validate_rejects_oversized(tmp_path):
    """Files over size limit are rejected."""
    from excel_report_bot.parser.validators import validate_file
    p = tmp_path / "big.xlsx"
    # Write a valid xlsx then check size logic by passing max_mb=0
    make_xlsx(str(p), ["Товар", "Количество", "Сумма", "Остаток"], [["A", 1, 100, 5]])
    ok, msg = validate_file(str(p), max_mb=0)
    assert not ok
    assert "MB" in msg or "размер" in msg.lower() or "большой" in msg.lower()


def test_validate_accepts_valid_xlsx(tmp_path):
    """Valid xlsx with required columns passes validation."""
    from excel_report_bot.parser.validators import validate_file
    p = tmp_path / "sales.xlsx"
    make_xlsx(str(p), ["Товар", "Количество", "Сумма", "Остаток"], [["A", 1, 100, 5]])
    ok, msg = validate_file(str(p), max_mb=10)
    assert ok, msg


def test_validate_rejects_missing_columns(tmp_path):
    """xlsx missing required columns fails with example header message."""
    from excel_report_bot.parser.validators import validate_file
    p = tmp_path / "bad.xlsx"
    make_xlsx(str(p), ["Дата", "Комментарий"], [["2026-01-01", "note"]])
    ok, msg = validate_file(str(p), max_mb=10)
    assert not ok
    assert "колонк" in msg.lower() or "column" in msg.lower()


# ── Parser ───────────────────────────────────────────────────────────────────

def test_parse_basic(tmp_path):
    """parse_excel returns correct revenue and positions."""
    from excel_report_bot.parser.excel_parser import parse_excel
    p = tmp_path / "sales.xlsx"
    make_xlsx(
        str(p),
        ["Товар", "Количество", "Сумма", "Остаток", "Категория"],
        [
            ["Товар А", 10, 1000.0, 10, "Еда"],
            ["Товар Б", 5, 500.0, 2, "Еда"],
            ["Товар В", 3, 300.0, 0, "Техника"],
        ],
    )
    result = parse_excel(str(p), "sales.xlsx")
    assert result.revenue == 1800.0
    assert result.positions == 3
    # avg_check = revenue / len(rows) = 1800 / 3 = 600
    assert result.avg_check == pytest.approx(600.0)


def test_parse_low_and_zero_stock(tmp_path):
    """parse_excel correctly identifies low_stock and zero_stock."""
    from excel_report_bot.parser.excel_parser import parse_excel
    p = tmp_path / "stock.xlsx"
    make_xlsx(
        str(p),
        ["Товар", "Количество", "Сумма", "Остаток"],
        [
            ["А", 1, 100, 3],   # low
            ["Б", 1, 200, 0],   # zero
            ["В", 1, 300, 10],  # ok
            ["Г", 1, 400, 4],   # low
        ],
    )
    result = parse_excel(str(p), "stock.xlsx")
    assert "А" in result.low_stock
    assert "Г" in result.low_stock
    assert "Б" in result.zero_stock
    assert "В" not in result.low_stock
    assert "В" not in result.zero_stock


def test_parse_top_products_share(tmp_path):
    """top_products contains max 5 items and total revenue matches."""
    from excel_report_bot.parser.excel_parser import parse_excel
    p = tmp_path / "top.xlsx"
    rows = [[f"Т{i}", 1, float(100 * i), 10] for i in range(1, 8)]
    make_xlsx(str(p), ["Товар", "Количество", "Сумма", "Остаток"], rows)
    result = parse_excel(str(p), "top.xlsx")
    assert len(result.top_products) == 5
    total = sum(r["revenue"] for r in result.top_products)
    assert total <= result.revenue


def test_parse_alias_detection(tmp_path):
    """Alternative column names (amount, name) are auto-detected."""
    from excel_report_bot.parser.excel_parser import parse_excel
    p = tmp_path / "alias.xlsx"
    make_xlsx(
        str(p),
        ["name", "qty", "amount", "stock"],
        [["Item A", 2, 200.0, 5]],
    )
    result = parse_excel(str(p), "alias.xlsx")
    assert result.revenue == 200.0


def test_parse_date_columns(tmp_path):
    """date_from and date_to are extracted when date column exists."""
    from excel_report_bot.parser.excel_parser import parse_excel
    p = tmp_path / "dated.xlsx"
    make_xlsx(
        str(p),
        ["Товар", "Количество", "Сумма", "Остаток", "Дата"],
        [
            ["А", 1, 100, 5, "2026-03-01"],
            ["Б", 1, 200, 5, "2026-03-15"],
            ["В", 1, 300, 5, "2026-03-31"],
        ],
    )
    result = parse_excel(str(p), "dated.xlsx")
    assert result.date_from == "2026-03-01"
    assert result.date_to == "2026-03-31"
    assert result.period_days == 31  # March 1–31 inclusive = 31 days


def test_parse_abc_analysis(tmp_path):
    """ABC analysis: class A covers ~80% of revenue, C has smallest items."""
    from excel_report_bot.parser.excel_parser import parse_excel
    p = tmp_path / "abc.xlsx"
    # А=900 (75%), Б=150 (12.5%), В=100 (8.3%), Г=50 (4.2%)
    # Cumulative: А=75% < 80% → A; А+Б=87.5% → B; А+Б+В=95.8% → B (>80% but <=95%);
    # А+Б+В+Г=100% → C
    make_xlsx(
        str(p),
        ["Товар", "Количество", "Сумма", "Остаток"],
        [
            ["А", 1, 900.0, 10],
            ["Б", 1, 150.0, 10],
            ["В", 1, 100.0, 10],
            ["Г", 1, 50.0, 10],
        ],
    )
    result = parse_excel(str(p), "abc.xlsx")
    abc = result.abc_analysis
    assert "А" in abc["A"]           # dominant product is class A
    assert "Г" in abc["C"]           # smallest product is class C
    assert len(abc["A"]) + len(abc["B"]) + len(abc["C"]) == 4  # all products classified


def test_parse_daily_revenue(tmp_path):
    """daily_revenue groups revenue by date correctly."""
    from excel_report_bot.parser.excel_parser import parse_excel
    p = tmp_path / "daily.xlsx"
    make_xlsx(
        str(p),
        ["Товар", "Количество", "Сумма", "Остаток", "Дата"],
        [
            ["А", 1, 100.0, 5, "2026-04-01"],
            ["Б", 1, 200.0, 5, "2026-04-01"],  # same day as А → combined
            ["В", 1, 300.0, 5, "2026-04-02"],
        ],
    )
    result = parse_excel(str(p), "daily.xlsx")
    assert len(result.daily_revenue) == 2
    day1 = next(d for d in result.daily_revenue if d["date"] == "2026-04-01")
    day2 = next(d for d in result.daily_revenue if d["date"] == "2026-04-02")
    assert day1["revenue"] == pytest.approx(300.0)
    assert day2["revenue"] == pytest.approx(300.0)


def test_parse_abc_empty_without_product_column(tmp_path):
    """ABC analysis returns empty dicts when product column is missing."""
    from excel_report_bot.parser.excel_parser import parse_excel
    p = tmp_path / "no_product.xlsx"
    make_xlsx(str(p), ["Количество", "Сумма"], [[1, 500.0], [2, 300.0]])
    result = parse_excel(str(p), "no_product.xlsx")
    assert result.abc_analysis == {"A": [], "B": [], "C": []}
