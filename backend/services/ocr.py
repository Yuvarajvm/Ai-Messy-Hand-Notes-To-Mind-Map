# services/ocr.py
import os
import io
from PIL import Image
import logging

logger = logging.getLogger(__name__)

# ========== GOOGLE CLOUD VISION ==========
_GCV_CLIENT = None

def _ensure_gcv_client():
    """Initialize Google Cloud Vision client (lazy loading)"""
    global _GCV_CLIENT
    if _GCV_CLIENT is not None:
        return _GCV_CLIENT
    
    try:
        from google.cloud import vision
        _GCV_CLIENT = vision.ImageAnnotatorClient()
        return _GCV_CLIENT
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Google Cloud Vision: {e}")


def gcv_extract_text(img: Image.Image, lang: str = "en") -> str:
    """
    Extract text using Google Cloud Vision
    Returns: plain text string
    """
    try:
        client = _ensure_gcv_client()
        
        # Convert PIL Image to bytes
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        content = buf.getvalue()
        
        # Create Vision API image
        from google.cloud import vision
        image = vision.Image(content=content)
        
        # Detect text
        response = client.text_detection(image=image)
        
        if response.error.message:
            raise Exception(response.error.message)
        
        # Extract full text
        if response.text_annotations:
            full_text = response.text_annotations[0].description
            return full_text
        else:
            return ""
            
    except Exception as e:
        logger.error(f"Google Vision OCR failed: {e}")
        return ""


def tesseract_extract_text(img: Image.Image, lang: str = "en") -> str:
    """
    Extract text using Tesseract (fallback)
    Returns: plain text string
    """
    try:
        import pytesseract
        
        # Configure Tesseract
        if os.name == "nt":  # Windows
            tesseract_cmd = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
            if os.path.exists(tesseract_cmd):
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
        # Extract text
        text = pytesseract.image_to_string(img, lang=lang)
        return text
        
    except Exception as e:
        logger.error(f"Tesseract OCR failed: {e}")
        return ""
