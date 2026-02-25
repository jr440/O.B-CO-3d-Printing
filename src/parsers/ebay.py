import re
from .base import ParseResult


def detect(text: str) -> bool:
    low = text.lower()
    return "ebay" in low or "order details" in low


def parse(text: str) -> ParseResult:
    normalized = re.sub(r"\s+", " ", text)

    lines: list[dict] = []

    sku_pattern = re.compile(r"\b([A-Z]{1,4}[0-9]{2,8}(?:-[A-Z0-9]+)?)\b")
    for match in sku_pattern.finditer(normalized):
        sku = match.group(1).upper()
        if sku in {"EBAY", "ORDER"}:
            continue
        start = max(0, match.start() - 120)
        end = min(len(normalized), match.end() + 240)
        ctx = normalized[start:end]

        material = "Unknown"
        for name in ("PLA", "PETG", "ABS", "ASA", "TPU", "NYLON"):
            if re.search(rf"\b{name}\b", ctx, re.I):
                material = name
                break

        if material == "Unknown":
            continue

        variant_match = re.search(r"([A-Za-z][A-Za-z0-9 +\-\/]{6,80})", ctx)
        variant = variant_match.group(1).strip() if variant_match else f"eBay Item {sku}"

        lines.append(
            {
                "sku": sku,
                "manufacturer": "SUNLU",
                "material": material,
                "variant": variant,
                "pack": "Unknown",
                "qtyKg": 1,
            }
        )

    deduped: dict[str, dict] = {line["sku"]: line for line in lines}
    parsed_lines = list(deduped.values())
    confidence = 0.65 if parsed_lines else 0.3
    return ParseResult(supplier="ebay", lines=parsed_lines, confidence=confidence)
