"""Parser package."""
from .excel_parser import parse_excel, ParseResult
from .validators import validate_file

__all__ = ["parse_excel", "ParseResult", "validate_file"]
