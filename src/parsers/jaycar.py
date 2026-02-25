import re
from .base import ParseResult


def detect(text: str) -> bool:
    low = text.lower()
    return "jaycar pty ltd" in low or "help.jaycar.com.au" in low or "tax invoice number" in low


def _material_from_name(name: str) -> str:
    upper = name.upper()
    if "SILK PLA" in upper or "PLA+" in upper:
        return "PLA Silk+"
    if "PLA PLUS" in upper:
        return "PLA+"
    if "PLA" in upper:
        return "PLA"
    if "PETG" in upper:
        return "PETG"
    if "ABS" in upper:
        return "ABS"
    if "TPU" in upper:
        return "TPU"
    if "NYLON" in upper:
        return "Nylon"
    return "Unknown"


def _manufacturer_from_name(name: str) -> str:
    match = re.match(r"\s*([A-Za-z][A-Za-z0-9+\-]*)", name)
    if not match:
        return "Unknown"
    return match.group(1)


def parse(text: str) -> ParseResult:
    lines = []
    row_pattern = re.compile(
        r"\b([A-Z]{2}\d{3,5})\b\s+(.+?)\s+(\d+)\s+\$[0-9]+(?:\.[0-9]{2})?\s+\$[0-9]+(?:\.[0-9]{2})?",
        re.IGNORECASE,
    )

    for match in row_pattern.finditer(text):
        code = match.group(1).upper()
        name = re.sub(r"\s+", " ", match.group(2)).strip()
        qty = int(match.group(3))

        name_upper = name.upper()
        is_filament = (
            "FILAMENT" in name_upper
            or " PLA" in f" {name_upper}"
            or "PETG" in name_upper
            or " ABS" in f" {name_upper}"
            or "TPU" in name_upper
            or "NYLON" in name_upper
        )
        if not is_filament:
            continue

        material = _material_from_name(name)
        manufacturer = _manufacturer_from_name(name)
        pack = "Refill" if "SPOOL-LESS" in name_upper or "SPOOLLESS" in name_upper else "Spool"

        lines.append(
            {
                "sku": code,
                "manufacturer": manufacturer,
                "material": material,
                "variant": name,
                "pack": pack,
                "qtyKg": qty,
            }
        )

    confidence = 0.9 if lines else 0.2
    return ParseResult(supplier="jaycar", lines=lines, confidence=confidence)
