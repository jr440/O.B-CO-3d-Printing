from dataclasses import dataclass


@dataclass
class ParseResult:
    supplier: str
    lines: list[dict]
    confidence: float
