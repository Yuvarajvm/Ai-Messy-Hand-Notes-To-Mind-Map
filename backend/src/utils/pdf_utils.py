# backend/src/utils/pdf_utils.py
from typing import List
from PIL import Image
import fitz  # PyMuPDF
import io

def pdf_to_images_bytes(pdf_bytes: bytes, dpi: int = 300) -> List[Image.Image]:
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    images = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            images.append(img)
    return images