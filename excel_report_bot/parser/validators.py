"""Validation of uploaded Excel files before parsing."""
import os
import openpyxl

EXAMPLE_HEADER = (
    "Пример правильной шапки:\n"
    "| Товар | Количество | Сумма | Остаток | Категория |\n\n"
    "Минимально необходимые колонки: Товар (или name/item), "
    "Количество (или qty/count), Сумма (или amount/revenue)."
)

REQUIRED_ALIASES = {
    "product":  ["товар", "наименование", "продукт", "name", "item"],
    "quantity": ["количество", "кол-во", "qty", "count"],
    "revenue":  ["сумма", "выручка", "amount", "revenue", "продажи"],
}


def _normalize(s: str) -> str:
    """Lowercase and strip a string."""
    return str(s).lower().strip()


def _detect_required(headers: list[str]) -> bool:
    """Return True if all required column groups are found."""
    normalized = [_normalize(h) for h in headers]
    for aliases in REQUIRED_ALIASES.values():
        if not any(n in aliases for n in normalized):
            return False
    return True


def validate_file(file_path: str, max_mb: int) -> tuple[bool, str]:
    """Validate uploaded file. Returns (ok, message)."""
    # 1. Extension check
    if not file_path.lower().endswith(".xlsx"):
        return False, (
            "❌ Неверный формат файла. Принимаются только файлы .xlsx\n"
            "(не .xls, не .csv, не .ods)\n\n" + EXAMPLE_HEADER
        )

    # 2. Size check
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > max_mb:
        return False, (
            f"❌ Файл слишком большой: {size_mb:.1f} MB (максимум {max_mb} MB).\n"
            "Пожалуйста, уменьшите файл или разбейте на несколько."
        )

    # 3. Valid xlsx check
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        headers = [str(cell.value) for cell in next(ws.iter_rows(max_row=1))]
        wb.close()
    except Exception as e:
        return False, (
            f"❌ Файл повреждён или не является корректным xlsx.\n"
            f"Детали: {e}\n\n" + EXAMPLE_HEADER
        )

    # 4. Required columns check
    if not _detect_required(headers):
        return False, (
            "❌ В файле не найдены обязательные колонки.\n"
            f"Найденные колонки: {', '.join(headers)}\n\n" + EXAMPLE_HEADER
        )

    return True, "OK"
