# services/ocr_pipeline.py
from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

# ========== OCR CONFIGURATION ==========
@dataclass
class OCRConfig:
    """Configuration for OCR processing"""
    engine: str = "gcv"
    lang: str = "en"
    dpi: int = 400
    deskew: bool = True
    denoise: bool = True
    binarize: bool = True
    morph: bool = True


# ========== MAIN OCR FUNCTION ==========
def extract_text_smart(file_path: str, config: OCRConfig) -> str:
    """
    Extract text from image or PDF
    Returns: plain text string
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()
    
    # Handle PDFs
    if suffix == ".pdf":
        try:
            # Import pdf_to_images function
            from src.utils.pdf_utils import pdf_to_images
            
            logger.info(f"Converting PDF to images: {file_path.name}")
            images = pdf_to_images(str(file_path), dpi=config.dpi)
            logger.info(f"PDF has {len(images)} pages")
            
            all_text = []
            for i, img in enumerate(images, 1):
                logger.info(f"Processing page {i}/{len(images)}")
                text = extract_text_from_image(img, config)
                if text and text.strip():
                    all_text.append(f"--- Page {i} ---\n{text}")
            
            result = "\n\n".join(all_text)
            logger.info(f"Extracted {len(result)} chars from {len(images)} pages")
            return result
            
        except ImportError as e:
            logger.error(f"PDF library not available: {e}")
            return ""
        except Exception as e:
            logger.error(f"PDF processing failed: {e}")
            return ""
    
    # Handle images
    else:
        try:
            img = Image.open(file_path)
            return extract_text_from_image(img, config)
        except Exception as e:
            logger.error(f"Image processing failed: {e}")
            return ""


def extract_text_from_image(img: Image.Image, config: OCRConfig) -> str:
    """Extract text from a single image using OCR"""
    try:
        # Preprocess if needed
        if config.deskew or config.denoise or config.binarize:
            try:
                from src.ocr.preprocess import preprocess_for_ocr
                img = preprocess_for_ocr(
                    img,
                    deskew=config.deskew,
                    denoise=config.denoise,
                    binarize=config.binarize,
                    morph=config.morph
                )
            except ImportError:
                logger.warning("Preprocessing not available, using raw image")
        
        # Use Google Cloud Vision
        if config.engine == "gcv":
            from services.ocr import gcv_extract_text
            text = gcv_extract_text(img, config.lang)
        else:
            from services.ocr import tesseract_extract_text
            text = tesseract_extract_text(img, config.lang)
        
        return text if text else ""
        
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}")
        return ""


# ========== HELPER FUNCTIONS ==========
def top_concepts(text: str, top_n: int = 10) -> list[dict]:
    """Extract top concepts from text"""
    try:
        from src.nlp.extract import get_nlp, extract_keyphrases
        
        nlp = get_nlp()
        doc = nlp(text[:50000])
        keyphrases = extract_keyphrases(doc, top_n=top_n)
        return keyphrases
        
    except Exception as e:
        logger.error(f"Concept extraction failed: {e}")
        return []


def cleanup_text(text: str) -> str:
    """Clean up extracted OCR text"""
    if not text:
        return ""
    
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    text = text.strip()
    
    return text
