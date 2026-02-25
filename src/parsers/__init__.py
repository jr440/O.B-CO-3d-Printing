from .base import ParseResult
from . import bambu, jaycar, ebay, generic


def parse_invoice(text: str) -> ParseResult:
    if bambu.detect(text):
        return bambu.parse(text)
    if jaycar.detect(text):
        return jaycar.parse(text)
    if ebay.detect(text):
        return ebay.parse(text)
    return generic.parse(text)
