import fitz  # PyMuPDF
from PIL import Image, ImageDraw
import io
from pathlib import Path
from urllib.request import urlopen
import hashlib

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


def _color_from_variant(variant: str, sku: str) -> tuple[int, int, int]:
    low = (variant or "").lower()
    palette = [
        (["white", "bone white", "ivory"], (218, 222, 232)),
        (["black", "charcoal"], (50, 52, 60)),
        (["grey", "gray", "silver"], (120, 124, 136)),
        (["pink", "magenta", "sakura"], (190, 120, 170)),
        (["red", "crimson"], (176, 78, 78)),
        (["blue", "sky", "cyan"], (96, 120, 190)),
        (["green", "mint", "olive"], (102, 144, 82)),
        (["yellow", "lemon", "gold"], (182, 164, 88)),
        (["orange", "mandarin"], (196, 122, 72)),
        (["purple", "violet"], (126, 104, 176)),
        (["brown", "chocolate", "cocoa", "wood"], (116, 95, 82)),
        (["beige"], (178, 156, 120)),
    ]
    for keys, color in palette:
        if any(k in low for k in keys):
            return color

    digest = hashlib.md5(sku.encode("utf-8")).digest()
    return (20 + digest[0] // 2, 26 + digest[1] // 2, 36 + digest[2] // 2)


def create_placeholder_thumbnail(
    out_path: str,
    sku: str,
    manufacturer: str,
    material: str,
    variant: str = "",
):
    """Create a simple fallback thumbnail card when no real product image exists."""
    bg_color = _color_from_variant(variant, sku)

    image = Image.new("RGB", (512, 512), bg_color)
    draw = ImageDraw.Draw(image)

    luminance = 0.2126 * bg_color[0] + 0.7152 * bg_color[1] + 0.0722 * bg_color[2]
    fg_color = (16, 22, 34) if luminance > 150 else (235, 240, 252)

    text_lines = [manufacturer or "Unknown", material or "Unknown", sku or "SKU"]
    y = 120
    for line in text_lines:
        draw.text((24, y), line[:32], fill=fg_color)
        y += 56

    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_file, "PNG")
