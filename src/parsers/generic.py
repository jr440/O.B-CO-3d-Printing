import re
from .base import ParseResult


def normalize_sku(sku: str) -> str:
    return sku.strip().upper()


def detect(text: str) -> bool:
    return True


def parse(text: str) -> ParseResult:
    normalized = re.sub(r"\s+", " ", text)
    sku_pattern = r"\b([A-Z0-9]{2,6}-[A-Z0-9]{1,4}-[0-9]+\.?[0-9]*-[0-9]{3,5}-[A-Za-z0-9]+)\b"

    lines = []
    for match in re.finditer(sku_pattern, normalized):
        sku = normalize_sku(match.group(1))
        start = max(0, match.start() - 120)
        end = min(len(normalized), match.end() + 220)
        ctx = normalized[start:end]

        variant_match = re.search(r"([A-Za-z][A-Za-z0-9 +\-\/]+)\s*\(\d{3,8}\)", ctx)
        variant = variant_match.group(0).strip() if variant_match else "Unknown"

        manufacturer = "Unknown"
        if variant != "Unknown":
            manufacturer_match = re.match(r"\s*([A-Za-z][A-Za-z0-9+\-]*)", variant)
            if manufacturer_match:
                manufacturer = manufacturer_match.group(1)

        material = "Unknown"
        for name in ("PLA", "PETG", "ABS", "ASA", "TPU", "NYLON"):
            if re.search(rf"\b{name}\b", ctx, re.I):
                material = name
                break

        qty_kg = 1
        qty_match = re.search(
            r"\bQty[: ]\s*(\d+)\b|\bQuantity[: ]\s*(\d+)\b|(\d+)\s*x\s*1\.0?\s*kg\b",
            ctx,
            re.I,
        )
        if qty_match:
            qty_kg = int(next(group for group in qty_match.groups() if group))

        if re.search(r"\brefill\b", ctx, re.I) or sku.endswith("-SPLFREE"):
            pack = "Refill"
        else:
            pack = "Spool"

        lines.append(
            {
                "sku": sku,
                "manufacturer": manufacturer,
                "material": material,
                "variant": variant,
                "pack": pack,
                "qtyKg": qty_kg,
            }
        )

    by_sku: dict[str, dict] = {}
    for line in lines:
        by_sku[line["sku"]] = line

    deduped = list(by_sku.values())
    confidence = 0.6 if deduped else 0.1
    return ParseResult(supplier="generic", lines=deduped, confidence=confidence)
