# services/ocr_pipeline.py
from __future__ import annotations
import os
import re
from dataclasses import dataclass
from typing import List, Dict, Any

import cv2
import numpy as np
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract

try:
    from google.cloud import vision
    _gcv_available = True
except Exception:
    _gcv_available = False


@dataclass
class OCRConfig:
    engine: str = "gcv"             # gcv | tesseract
    lang: str = "en"                # OCR language; Tesseract maps 'en' -> 'eng'
    dpi: int = 400
    deskew: bool = True
    denoise: bool = True
    binarize: bool = True
    morph: bool = True
    merge_columns: bool = True
    drop_low_conf: float = 0.0
    strip_headers_footers: bool = True


# ---- PDF gate ----
def pdf_has_text(pdf_path: str) -> bool:
    with fitz.open(pdf_path) as doc:
        for page in doc:
            t = page.get_text("text")
            if t and t.strip():
                return True
    return False


def extract_text_from_pdf_no_ocr(pdf_path: str) -> str:
    with fitz.open(pdf_path) as doc:
        parts = [page.get_text("text").strip() for page in doc]
    return "\n\n".join(parts).strip()


# ---- Preprocess ----
def _deskew(gray: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(gray < 250))
    if coords.size == 0:
        return gray
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_image_bgr(img_bgr: np.ndarray, cfg: OCRConfig) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    if cfg.denoise:
        gray = cv2.bilateralFilter(gray, 7, 60, 60)
    if cfg.deskew:
        gray = _deskew(gray)
    if cfg.binarize:
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        bw = gray
    if cfg.morph:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel, iterations=1)
    return bw


def pdf_to_images_bgr(pdf_path: str, dpi: int = 400) -> List[np.ndarray]:
    poppler_path = os.environ.get("POPPLER_PATH")  # required on Windows
    pages = convert_from_path(pdf_path, dpi=dpi, poppler_path=poppler_path)
    return [cv2.cvtColor(np.array(p), cv2.COLOR_RGB2BGR) for p in pages]


# ---- OCR engines ----
def gcv_document_text_from_bytes(content: bytes, lang: str = "en"):
    if not _gcv_available:
        raise RuntimeError("google-cloud-vision not installed/available.")
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is not set.")
    client = vision.ImageAnnotatorClient()
    img = vision.Image(content=content)
    resp = client.document_text_detection(
        image=img,
        image_context=vision.ImageContext(language_hints=[lang])
    )
    if resp.error.message:
        raise RuntimeError(resp.error.message)
    return resp.full_text_annotation


def _bbox_key(bbox) -> tuple:
    xs = [v.x for v in bbox.vertices]
    ys = [v.y for v in bbox.vertices]
    return (min(ys), min(xs))


def rebuild_paragraphs_from_gcv(fta, merge_columns: bool = True, drop_low_conf: float = 0.0) -> str:
    paragraphs: List[str] = []
    for page in fta.pages:
        blocks = sorted(page.blocks, key=lambda b: _bbox_key(b.bounding_box))
        if merge_columns and blocks:
            centers = [sum(v.x for v in b.bounding_box.vertices) / 4.0 for b in blocks]
            mid = (min(centers) + max(centers)) / 2.0
            left = [b for b, c in zip(blocks, centers) if c <= mid]
            right = [b for b, c in zip(blocks, centers) if c > mid]
            ordered = left + right
        else:
            ordered = blocks

        for b in ordered:
            for p in b.paragraphs:
                words = []
                for w in p.words:
                    token = "".join(s.text for s in w.symbols)
                    conf = getattr(w, "confidence", 1.0)
                    if conf is not None and conf < drop_low_conf:
                        continue
                    words.append(token)
                txt = " ".join(words).strip()
                if txt:
                    paragraphs.append(txt)
    text = "\n\n".join(paragraphs)
    return cleanup_text(text)


def tesseract_text_from_image(bw: np.ndarray, lang: str = "eng", psm: int = 6, oem: int = 1) -> str:
    config = f"--oem {oem} --psm {psm}"
    txt = pytesseract.image_to_string(bw, lang=lang, config=config)
    return cleanup_text(txt)


# ---- Cleanup + headers/footers ----
def cleanup_text(text: str) -> str:
    text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
    text = re.sub(r'(?<![.!?:;])\n(?!\n)', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def strip_headers_footers_by_frequency(page_texts: List[str], min_ratio: float = 0.4) -> List[str]:
    from collections import Counter
    lines = []
    for p in page_texts:
        for ln in (p or "").splitlines():
            lines.append(ln.strip())
    total_pages = max(1, len(page_texts))
    c = Counter(lines)
    common = {line for line, cnt in c.items() if cnt >= max(2, int(min_ratio * total_pages))}
    cleaned_pages = []
    for p in page_texts:
        kept = "\n".join(ln for ln in p.splitlines() if ln.strip() not in common)
        cleaned_pages.append(kept.strip())
    return cleaned_pages


# ---- Smart extractor ----
def extract_text_smart(path: str, cfg: OCRConfig) -> Dict[str, Any]:
    if path.lower().endswith(".pdf"):
        if pdf_has_text(path):
            txt = extract_text_from_pdf_no_ocr(path)
            return {"text": cleanup_text(txt), "engine_used": "none", "pages": _pdf_page_count(path)}

        images = pdf_to_images_bgr(path, dpi=cfg.dpi)
        page_texts: List[str] = []
        for img in images:
            bw = preprocess_image_bgr(img, cfg)
            if cfg.engine == "gcv":
                ok, buf = cv2.imencode(".png", bw)
                fta = gcv_document_text_from_bytes(buf.tobytes(), lang=cfg.lang)
                page_txt = rebuild_paragraphs_from_gcv(fta, merge_columns=cfg.merge_columns, drop_low_conf=cfg.drop_low_conf)
            else:
                page_txt = tesseract_text_from_image(bw, lang=_tesseract_lang(cfg.lang), psm=6, oem=1)
            page_texts.append(page_txt)

        if cfg.strip_headers_footers and len(page_texts) > 1:
            page_texts = strip_headers_footers_by_frequency(page_texts)

        return {"text": cleanup_text("\n\n".join(page_texts)), "engine_used": cfg.engine, "pages": len(page_texts)}

    # Single image
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Cannot read file: {path}")
    bw = preprocess_image_bgr(img, cfg)
    if cfg.engine == "gcv":
        ok, buf = cv2.imencode(".png", bw)
        fta = gcv_document_text_from_bytes(buf.tobytes(), lang=cfg.lang)
        txt = rebuild_paragraphs_from_gcv(fta, merge_columns=cfg.merge_columns, drop_low_conf=cfg.drop_low_conf)
        engine_used = "gcv"
    else:
        txt = tesseract_text_from_image(bw, lang=_tesseract_lang(cfg.lang), psm=6, oem=1)
        engine_used = "tesseract"
    return {"text": txt, "engine_used": engine_used, "pages": 1}


def _pdf_page_count(path: str) -> int:
    with fitz.open(path) as doc:
        return len(doc)


def _tesseract_lang(lang: str) -> str:
    return {"en": "eng"}.get(lang, lang)


# ---- lightweight concept extraction (used by /ocr/process) ----
def top_concepts(text: str, k: int = 10) -> List[str]:
    import math
    from collections import Counter
    tokens = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower())
    stop = _default_stopwords()
    tokens = [t for t in tokens if t not in stop]
    c = Counter(tokens)
    top = [w for w, _ in c.most_common(k * 3)]
    seen = set()
    result = []
    for w in top:
        root = w[:6]
        if root in seen:
            continue
        seen.add(root)
        result.append(w)
        if len(result) >= k:
            break
    return result


def _default_stopwords():
    return set("""
a about above after again against all am an and any are aren't as at be because been before being below between both
but by can't cannot could couldn't did didn't do does doesn't doing don't down during each few for from further had
hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his how how's i i'd
i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor not of off on once
only or other ought our ours ourselves out over own same shan't she she'd she'll she's should shouldn't so some such
than that that's the their theirs them themselves then there there's these they they'd they'll they're they've this those
through to too under until up very was wasn't we we'd we'll we're we've were weren't what what's when when's where where's
which while who who's whom why why's with won't would wouldn't you you'd you'll you're you've your yours yourself yourselves
    """.split())