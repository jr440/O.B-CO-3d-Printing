import fitz  # PyMuPDF
from PIL import Image
import io

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


def extract_images_from_pdf(pdf_path: str) -> list[bytes]:
    """
    Alternative: extract embedded images directly from PDF.
    This is less reliable than render+crop, but can work if images are cleanly embedded.
    """
    doc = fitz.open(pdf_path)
    images = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images()
        
        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            images.append(image_bytes)
    
    doc.close()
    return images
