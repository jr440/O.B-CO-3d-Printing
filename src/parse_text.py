import re

def parse_invoice_text_to_lines(text: str) -> list[dict]:
    """
    Extract line items from invoice text.
    Returns list of dicts: {sku, material, variant, pack, qtyKg}
    """
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # SKU pattern: e.g. A00-D0-1.75-1000-spl
    sku_pattern = r'\b([A-Z]\d{2}-[A-Z0-9]{1,2}-1\.75-\d{4}-[A-Za-z0-9]+)\b'
    
    lines = []
    for match in re.finditer(sku_pattern, text):
        sku = match.group(1)
        
        # Get context around SKU (±120 chars)
        start = max(0, match.start() - 120)
        end = min(len(text), match.end() + 220)
        ctx = text[start:end]
        
        # Guess material
        if re.search(r'PLA Silk\+?', ctx, re.I):
            material = "PLA Silk+"
        elif re.search(r'PLA Matte', ctx, re.I):
            material = "PLA Matte"
        elif re.search(r'PLA Translucent', ctx, re.I):
            material = "PLA Translucent"
        elif re.search(r'\bPLA\b', ctx, re.I):
            material = "PLA Basic"
        elif re.search(r'\bABS\b', ctx, re.I):
            material = "ABS"
        else:
            material = "Unknown"
        
        # Variant: usually "Name (12345)"
        variant_match = re.search(r'([A-Za-z][A-Za-z0-9 +\-\/]+)\s*\(\d{5}\)', ctx)
        variant = variant_match.group(0).strip() if variant_match else "Unknown"
        
        # Qty
        qty_kg = 1
        qty_match = re.search(r'\bQty[: ]\s*(\d+)\b|\bQuantity[: ]\s*(\d+)\b|(\d+)\s*x\s*1\.0?\s*kg\b', ctx, re.I)
        if qty_match:
            qty_kg = int(next(g for g in qty_match.groups() if g))
        
        # Pack
        pack = "Refill" if (re.search(r'refill', ctx, re.I) or 'SPLFREE' in sku.upper()) else "Spool"
        
        lines.append({
            "sku": sku,
            "material": material,
            "variant": variant,
            "pack": pack,
            "qtyKg": qty_kg
        })
    
    # Deduplicate
    seen = set()
    unique = []
    for line in lines:
        key = f"{line['sku']}|{line['variant']}|{line['pack']}"
        if key not in seen:
            seen.add(key)
            unique.append(line)
    
    return unique
