import re
from .base import ParseResult


def normalize_sku(sku: str) -> str:
    return sku.strip().upper()


def detect(text: str) -> bool:
    low = text.lower()
    return (
        "bambu lab" in low
        or "tuozhu technology" in low
        or "au.store.bambulab.com" in low
        or "invoice number: bblau" in low
    )


def parse(text: str) -> ParseResult:
    normalized = re.sub(r"\s+", " ", text)
    sku_pattern = r"\b([A-Z]\d{2}-[A-Z0-9]{1,2}-1\.75-\d{4}-[A-Za-z0-9]+)\b"

    lines = []
    for match in re.finditer(sku_pattern, normalized):
        sku = normalize_sku(match.group(1))

        start = max(0, match.start() - 120)
        end = min(len(normalized), match.end() + 220)
        ctx = normalized[start:end]

        if re.search(r"PLA Silk\+?", ctx, re.I):
            material = "PLA Silk+"
        elif re.search(r"PLA Matte", ctx, re.I):
            material = "PLA Matte"
        elif re.search(r"PLA Translucent", ctx, re.I):
            material = "PLA Translucent"
        elif re.search(r"\bPLA\b", ctx, re.I):
            material = "PLA Basic"
        elif re.search(r"\bABS\b", ctx, re.I):
            material = "ABS"
        else:
            material = "Unknown"

        variant_match = re.search(r"([A-Za-z][A-Za-z0-9 +\-\/]+)\s*\(\d{5}\)", ctx)
        variant = variant_match.group(0).strip() if variant_match else "Unknown"

        qty_kg = 1
        qty_match = re.search(
            r"\bQty[: ]\s*(\d+)\b|\bQuantity[: ]\s*(\d+)\b|(\d+)\s*x\s*1\.0?\s*kg\b",
            ctx,
            re.I,
        )
        if qty_match:
            qty_kg = int(next(group for group in qty_match.groups() if group))

        if sku.endswith("-SPLFREE"):
            pack = "Refill"
        elif sku.endswith("-SPL"):
            pack = "Spool"
        elif re.search(r"\brefill\b", ctx, re.I):
            pack = "Refill"
        else:
            pack = "Spool"

        lines.append(
            {
                "sku": sku,
                "manufacturer": "Bambu Lab",
                "material": material,
                "variant": variant,
                "pack": pack,
                "qtyKg": qty_kg,
            }
        )

    by_sku: dict[str, dict] = {}
    for line in lines:
        key = line["sku"]
        existing = by_sku.get(key)
        if existing is None:
            by_sku[key] = line
            continue

        existing_unknowns = sum(
            1 for field in ("material", "variant") if existing.get(field) == "Unknown"
        )
        current_unknowns = sum(
            1 for field in ("material", "variant") if line.get(field) == "Unknown"
        )
        if current_unknowns < existing_unknowns:
            by_sku[key] = line

    deduped = list(by_sku.values())
    confidence = 0.95 if deduped else 0.2
    return ParseResult(supplier="bambu", lines=deduped, confidence=confidence)
