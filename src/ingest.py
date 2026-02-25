#!/usr/bin/env python3
import json
import sys
import re
from pathlib import Path
from datetime import datetime
import fitz  # PyMuPDF
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from parse_text import parse_invoice_text
from render_and_crop import (
    render_first_page_to_png,
    crop_thumbnail_from_page_png,
    extract_product_images_from_pdf,
    save_image_bytes_as_png,
    save_image_source_as_png,
    create_placeholder_thumbnail,
)
from build_site import build_site

INVOICES_DIR = Path("invoices")
DB_PATH = Path("site/db.json")
IMAGES_DIR = Path("site/images")
TMP_DIR = Path(".tmp")
IMAGE_MAP_PATH = Path("image_map.json")
LINE_OVERRIDES_PATH = Path("line_overrides.json")


def _to_title_words(value: str) -> str:
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value.title()


def extract_ebay_lines_from_ocr(pdf_path: Path) -> list[dict]:
    """Use OCR on eBay order PDFs to recover item code and material/color details."""
    try:
        import numpy as np
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return []

    doc = fitz.open(pdf_path)
    ocr = RapidOCR()
    texts: list[str] = []

    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        arr = np.array(image)
        result, _ = ocr(arr)
        for line in result or []:
            line_text = str(line[1]).strip()
            if line_text:
                texts.append(line_text)

    doc.close()
    if not texts:
        return []

    joined = " | ".join(texts)
    item_numbers = re.findall(r"Item\s*number\s*[:：]?\s*(\d{9,15})", joined, re.I)
    item_code = item_numbers[0] if item_numbers else ""

    variants: list[str] = []
    seen: set[str] = set()
    for text in texts:
        low = text.lower()
        if "petg" not in low:
            continue
        if "return" in low or "accepted" in low:
            continue

        normalized = text.replace("·", " ").replace("•", " ")
        variant = ""

        matte_match = re.search(r"matte\s*([a-zA-Z ]{2,40}?)\s*petg", normalized, re.I)
        if matte_match:
            color = _to_title_words(matte_match.group(1))
            if any(token in color.lower() for token in ("sunlu", "printer", "filament", "pla")):
                continue
            variant = f"Matte {color} · PETG (Matte)"
        else:
            color_match = re.search(r"([a-zA-Z ]{2,40}?)\s*petg", normalized, re.I)
            if not color_match:
                continue
            color = _to_title_words(color_match.group(1))
            color = re.sub(r"\bItemnumber\b", "", color, flags=re.I).strip()
            color = re.sub(r"\bFilament\b", "", color, flags=re.I).strip()
            if any(token in color.lower() for token in ("sunlu", "printer", "filament", "pla", "itemnumber")):
                continue
            if len(color) < 2:
                continue
            variant = f"{color} · PETG"

        if variant in seen:
            continue
        seen.add(variant)
        variants.append(variant)

    if not variants:
        return []

    lines: list[dict] = []
    stem = re.sub(r"[^A-Z0-9]+", "-", pdf_path.stem.upper()).strip("-")
    for index, variant in enumerate(variants, start=1):
        sku = item_code if item_code else f"EBY-{stem}-{index:02d}"
        if item_code:
            sku = f"{item_code}-{index:02d}"
        lines.append(
            {
                "sku": sku,
                "manufacturer": "SUNLU",
                "material": "PETG",
                "variant": variant,
                "pack": "Spool",
                "qtyKg": 1,
            }
        )

    return lines


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all text from PDF"""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    doc.close()
    return text


def load_db() -> list[dict]:
    """Load database JSON"""
    if DB_PATH.exists():
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_db(db: list[dict]):
    """Save database JSON"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)


def invoice_key_from_filename(pdf_path: Path) -> str:
    """Use filename as unique key"""
    return pdf_path.name


def make_ebay_fallback_lines(pdf_path: Path, count: int) -> list[dict]:
    """Create synthetic line items for eBay invoices when text extraction is unreadable."""
    base = re.sub(r"[^A-Z0-9]+", "-", pdf_path.stem.upper()).strip("-")
    lines = []
    for index in range(count):
        lines.append(
            {
                "sku": f"EBY-{base}-{index + 1:02d}",
                "manufacturer": "SUNLU",
                "material": "Filament",
                "variant": f"eBay Filament Item {index + 1}",
                "pack": "Unknown",
                "qtyKg": 1,
            }
        )
    return lines


def load_image_map() -> dict[str, str]:
    """Load optional SKU->imageSource map from image_map.json."""
    if not IMAGE_MAP_PATH.exists():
        return {}
    try:
        with open(IMAGE_MAP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k).upper(): str(v) for k, v in data.items()}
    except Exception as e:
        print(f"  Warning: couldn't load image map: {e}")
    return {}


def load_line_overrides() -> dict[str, dict]:
    """Load optional SKU->line field overrides from line_overrides.json."""
    if not LINE_OVERRIDES_PATH.exists():
        return {}
    try:
        with open(LINE_OVERRIDES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            normalized: dict[str, dict] = {}
            for key, value in data.items():
                if isinstance(value, dict):
                    normalized[str(key).upper()] = value
            return normalized
    except Exception as e:
        print(f"  Warning: couldn't load line overrides: {e}")
    return {}


def apply_line_overrides(lines: list[dict], overrides: dict[str, dict]) -> int:
    """Apply per-SKU metadata overrides to parsed line items."""
    if not overrides:
        return 0

    allowed_fields = {"manufacturer", "material", "variant", "pack", "qtyKg"}
    applied = 0
    for line in lines:
        sku = str(line.get("sku", "")).upper()
        if not sku or sku not in overrides:
            continue
        data = overrides[sku]
        for field, value in data.items():
            if field in allowed_fields:
                line[field] = value
        applied += 1
    return applied


def apply_image_map_for_lines(lines: list[dict], image_map: dict[str, str]) -> set[str]:
    """Apply mapped image sources to line-item SKU thumbnails."""
    if not image_map:
        return set()

    mapped_skus: set[str] = set()
    for line in lines:
        sku = str(line.get("sku", "")).upper()
        if not sku:
            continue
        source = image_map.get(sku)
        if not source:
            continue

        resolved_source = source
        if not source.lower().startswith("http://") and not source.lower().startswith("https://"):
            source_path = Path(source)
            if not source_path.is_absolute():
                source_path = Path(os.getcwd()) / source_path
            resolved_source = str(source_path)

        out_thumb = IMAGES_DIR / f"{sku}.png"
        try:
            save_image_source_as_png(resolved_source, str(out_thumb))
            mapped_skus.add(sku)
        except Exception as e:
            print(f"  Warning: couldn't apply mapped image for {sku}: {e}")

    return mapped_skus


def ingest_one(pdf_path: Path) -> dict:
    """Process a single PDF invoice"""
    print(f"Ingesting: {pdf_path.name}")
    
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Extract text and parse
    text = extract_text_from_pdf(pdf_path)
    parsed = parse_invoice_text(text)
    lines = parsed.lines
    image_map = load_image_map()
    line_overrides = load_line_overrides()
    
    product_images = extract_product_images_from_pdf(str(pdf_path))
    is_ebay_file = "ebay" in pdf_path.name.lower()

    if is_ebay_file and parsed.supplier == "generic":
        parsed.supplier = "ebay"
        parsed.confidence = max(parsed.confidence, 0.4)

    if is_ebay_file:
        ocr_lines = extract_ebay_lines_from_ocr(pdf_path)
        if ocr_lines:
            lines = ocr_lines
            parsed.supplier = "ebay"
            parsed.confidence = max(parsed.confidence, 0.85)
            print(f"  ✓ OCR extracted {len(lines)} eBay line item(s)")

    if (parsed.supplier == "ebay" or is_ebay_file) and not lines and product_images:
        lines = make_ebay_fallback_lines(pdf_path, len(product_images))
        parsed.supplier = "ebay"
        parsed.confidence = 0.5
        print(f"  Info: eBay fallback created {len(lines)} line item(s) from embedded product images")

    overrides_applied = apply_line_overrides(lines, line_overrides)
    if overrides_applied:
        print(f"  ✓ Applied {overrides_applied} line override(s)")

    used_embedded = 0
    embedded_skus: set[str] = set()

    if product_images:
        for i, line in enumerate(lines):
            if i >= len(product_images):
                break
            out_thumb = IMAGES_DIR / f"{line['sku']}.png"
            try:
                save_image_bytes_as_png(product_images[i], str(out_thumb))
                used_embedded += 1
                embedded_skus.add(str(line.get("sku", "")).upper())
            except Exception as e:
                print(f"  Warning: couldn't save embedded image for {line['sku']}: {e}")

    if used_embedded == 0 and parsed.supplier == "bambu":
        page_png = TMP_DIR / f"{pdf_path.stem}.page1.png"
        render_first_page_to_png(str(pdf_path), str(page_png))

        try:
            for line in lines:
                out_thumb = IMAGES_DIR / f"{line['sku']}.png"
                try:
                    crop_thumbnail_from_page_png(str(page_png), str(out_thumb))
                except Exception as e:
                    print(f"  Warning: couldn't crop thumbnail for {line['sku']}: {e}")
        finally:
            try:
                if page_png.exists():
                    page_png.unlink()
            except Exception as e:
                print(f"  Warning: couldn't remove temp file {page_png.name}: {e}")
    elif used_embedded == 0:
        print("  Info: no embedded product images found for this supplier; skipping thumbnail fallback")

    mapped_skus = apply_image_map_for_lines(lines, image_map)
    if mapped_skus:
        print(f"  ✓ Applied {len(mapped_skus)} mapped image(s)")

    placeholder_images = 0
    for line in lines:
        sku = str(line.get("sku", "")).upper()
        if not sku:
            continue
        if sku in embedded_skus or sku in mapped_skus:
            continue

        out_thumb = IMAGES_DIR / f"{sku}.png"
        should_refresh_placeholder = parsed.supplier in {"jaycar", "generic"}
        if out_thumb.exists() and not should_refresh_placeholder:
            continue

        create_placeholder_thumbnail(
            str(out_thumb),
            sku,
            str(line.get("manufacturer", "Unknown")),
            str(line.get("material", "Unknown")),
            str(line.get("variant", "")),
        )
        placeholder_images += 1

    if placeholder_images:
        print(f"  ✓ Created {placeholder_images} placeholder image(s)")
    
    return {
        "sourceFile": invoice_key_from_filename(pdf_path),
        "ingestedAt": datetime.now().isoformat(),
        "supplier": parsed.supplier,
        "parseConfidence": parsed.confidence,
        "lines": lines
    }


def ingest_all(reprocess_existing: bool = False):
    """Process all PDFs in invoices/ folder"""
    INVOICES_DIR.mkdir(exist_ok=True)
    
    pdf_files = list(INVOICES_DIR.glob("*.pdf"))
    db = load_db()
    
    existing = {inv["sourceFile"] for inv in db}
    newly_ingested = 0
    failed = 0
    
    for pdf_path in pdf_files:
        if not reprocess_existing and pdf_path.name in existing:
            continue

        try:
            invoice = ingest_one(pdf_path)
            replaced = False
            for idx, existing_invoice in enumerate(db):
                if existing_invoice.get("sourceFile") == invoice["sourceFile"]:
                    db[idx] = invoice
                    replaced = True
                    break
            if not replaced:
                db.append(invoice)
            save_db(db)
            newly_ingested += 1
        except Exception as e:
            failed += 1
            print(f"✗ Failed to ingest {pdf_path.name}: {e}")
    
    build_site(str(DB_PATH))
    print(f"✓ Ingested {newly_ingested} new invoice(s)")
    if failed:
        print(f"⚠ Skipped {failed} invoice(s) due to errors")


class InvoiceHandler(FileSystemEventHandler):
    """Watch for new PDFs"""
    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.lower().endswith(".pdf"):
            print(f"\n→ New PDF detected: {Path(event.src_path).name}")
            ingest_all()


def watch_invoices():
    """Watch invoices/ folder for new PDFs"""
    INVOICES_DIR.mkdir(exist_ok=True)
    event_handler = InvoiceHandler()
    observer = Observer()
    observer.schedule(event_handler, str(INVOICES_DIR), recursive=False)
    observer.start()
    
    print(f"👀 Watching {INVOICES_DIR}/ for new PDFs... (Ctrl+C to stop)")
    
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    if "--watch" in sys.argv:
        ingest_all()  # Process existing first
        watch_invoices()
    else:
        ingest_all()
