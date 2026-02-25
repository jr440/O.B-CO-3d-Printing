from parsers import parse_invoice
from parsers.base import ParseResult


def parse_invoice_text(text: str) -> ParseResult:
    return parse_invoice(text)


def parse_invoice_text_to_lines(text: str) -> list[dict]:
    """Compatibility helper returning only parsed lines."""
    return parse_invoice(text).lines
