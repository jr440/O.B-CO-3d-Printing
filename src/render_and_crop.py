import fitz  # PyMuPDF
from PIL import Image
import io
from pathlib import Path
from urllib.request import urlopen

# Adjust after you confirm invoice layout
RENDER_DPI = 150

# Placeholder crop box (pixels in rendered image space)
# Format: (left, top, right, bottom)
# You'll need to adjust this once we see your invoice layout
CROP_BOX = (40, 260, 260, 480)


def render_first_page_to_png(pdf_path: str, out_png_path: str):
    """Render first page of PDF to PNG"""
    doc = fitz.open(pdf_path)
    page = doc[0]
    
    # Render to pixmap
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    pix = page.get_pixmap(matrix=mat)
    
    # Save as PNG
    pix.save(out_png_path)
    doc.close()


def crop_thumbnail_from_page_png(page_png_path: str, out_thumb_path: str):
    """Crop a fixed region from the rendered page"""
    img = Image.open(page_png_path)
    thumb = img.crop(CROP_BOX)
    thumb.save(out_thumb_path, "PNG")


def extract_product_images_from_pdf(pdf_path: str) -> list[bytes]:
    """Extract likely product images from PDF (large near-square embedded images)."""
    doc = fitz.open(pdf_path)
    images: list[bytes] = []
    seen_xrefs: set[int] = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_info in image_list:
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            base_image = doc.extract_image(xref)
            width = int(base_image.get("width", 0))
            height = int(base_image.get("height", 0))
            if width < 500 or height < 300:
                continue

            ratio = width / height if height else 0
            if ratio < 0.7 or ratio > 1.4:
                continue

            image_bytes = base_image["image"]
            images.append(image_bytes)

    doc.close()
    return images


def save_image_bytes_as_png(image_bytes: bytes, out_path: str):
    """Save any supported image bytes as a PNG file."""
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(io.BytesIO(image_bytes)) as img:
        img.convert("RGB").save(out_file, "PNG")


def save_image_source_as_png(source: str, out_path: str):
    """Save image from local path or URL as PNG."""
    source = source.strip()
    if source.lower().startswith("http://") or source.lower().startswith("https://"):
        with urlopen(source, timeout=20) as response:
            image_bytes = response.read()
    else:
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"Image source not found: {source}")
        image_bytes = source_path.read_bytes()

    save_image_bytes_as_png(image_bytes, out_path)
