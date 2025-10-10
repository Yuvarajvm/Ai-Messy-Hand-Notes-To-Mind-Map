import os
import io
import shutil
import pytesseract
from PIL import Image
from .preprocess import pil_to_cv2, preprocess_for_ocr

# Configure Tesseract path on Windows if needed (fallback engine)
def _setup_tesseract_path():
    cmd = os.getenv("TESSERACT_CMD")
    if cmd and os.path.exists(cmd):
        pytesseract.pytesseract.tesseract_cmd = cmd
        return
    if os.name == "nt":
        default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(default):
            pytesseract.pytesseract.tesseract_cmd = default
            return
    if shutil.which("tesseract") is None:
        # If not found, OCR will fail when using tesseract engine
        pass

_setup_tesseract_path()

# ---------- Google Cloud Vision ----------
_GCV_CLIENT = None

def _ensure_gcv_client():
    global _GCV_CLIENT
    if _GCV_CLIENT is not None:
        return _GCV_CLIENT
    try:
        from google.cloud import vision
        _GCV_CLIENT = vision.ImageAnnotatorClient()
        return _GCV_CLIENT
    except Exception as e:
        raise RuntimeError(
            "Failed to initialize Google Cloud Vision client. "
            "Ensure google-cloud-vision is installed and "
            "GOOGLE_APPLICATION_CREDENTIALS points to your service account JSON."
        ) from e

def _map_lang(lang: str) -> str:
    # Map Tesseract-style 'eng' to BCP-47 'en'
    if lang.lower().startswith("eng"):
        return "en"
    return lang

def _ocr_gcv(pil_img: Image.Image, lang: str = "eng") -> str:
    from google.cloud import vision
    client = _ensure_gcv_client()
    # Use JPEG to reduce payload size; Vision handles color/contrast well
    buf = io.BytesIO()
    pil_img.convert("RGB").save(buf, format="JPEG", quality=90)
    content = buf.getvalue()
    image = vision.Image(content=content)
    image_context = vision.ImageContext(language_hints=[_map_lang(lang)])
    response = client.document_text_detection(image=image, image_context=image_context)

    if response.error.message:
        raise RuntimeError(f"Vision API error: {response.error.message}")

    if response.full_text_annotation and response.full_text_annotation.text:
        return response.full_text_annotation.text.strip()

    # Fallback if full_text_annotation is empty
    if response.text_annotations:
        return response.text_annotations[0].description.strip()

    return ""

# ---------- Tesseract (fallback/offline) ----------
def _ocr_tesseract(pil_img: Image.Image, lang: str = "eng", mode: str = "block") -> str:
    # mode: "block" (psm 6), "line" (psm 7), "sparse" (psm 11)
    img_bgr = pil_to_cv2(pil_img)
    pre = preprocess_for_ocr(img_bgr)  # binarize/denoise
    rgb = Image.fromarray(pre).convert("RGB")
    psm_map = {"block": "6", "line": "7", "sparse": "11"}
    psm = psm_map.get(mode, "6")
    config = f"--oem 1 --psm {psm}"
    txt = pytesseract.image_to_string(rgb, lang=lang, config=config)
    return txt.strip()

# ---------- Public function ----------
def ocr_image_pil(pil_img: Image.Image, lang: str = "eng", engine: str = "gcv", mode: str = "block") -> str:
    """
    engine: "gcv" (Google Cloud Vision) | "tesseract"
    mode: used only by tesseract ("block" | "line" | "sparse")
    """
    engine = (engine or "gcv").lower()
    if engine == "gcv":
        return _ocr_gcv(pil_img, lang=lang)
    return _ocr_tesseract(pil_img, lang=lang, mode=mode)