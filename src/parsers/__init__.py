from .base import ParseResult
from . import bambu, jaycar, generic


def parse_invoice(text: str) -> ParseResult:
    if bambu.detect(text):
        return bambu.parse(text)
    if jaycar.detect(text):
        return jaycar.parse(text)
    return generic.parse(text)
