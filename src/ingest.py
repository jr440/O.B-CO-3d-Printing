#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from datetime import datetime
import fitz  # PyMuPDF
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from parse_text import parse_invoice_text
from render_and_crop import (
    render_first_page_to_png,
    crop_thumbnail_from_page_png,
    extract_product_images_from_pdf,
    save_image_bytes_as_png,
)
from build_site import build_site

INVOICES_DIR = Path("invoices")
DB_PATH = Path("site/db.json")
IMAGES_DIR = Path("site/images")
TMP_DIR = Path(".tmp")


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


def ingest_one(pdf_path: Path) -> dict:
    """Process a single PDF invoice"""
    print(f"Ingesting: {pdf_path.name}")
    
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Extract text and parse
    text = extract_text_from_pdf(pdf_path)
    parsed = parse_invoice_text(text)
    lines = parsed.lines
    
    product_images = extract_product_images_from_pdf(str(pdf_path))
    used_embedded = 0

    if product_images:
        for i, line in enumerate(lines):
            if i >= len(product_images):
                break
            out_thumb = IMAGES_DIR / f"{line['sku']}.png"
            try:
                save_image_bytes_as_png(product_images[i], str(out_thumb))
                used_embedded += 1
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
