# src/utils/pdf_utils.py
import os
from pathlib import Path
from typing import List
from PIL import Image

def pdf_to_images(pdf_path: str, dpi: int = 300) -> List[Image.Image]:
    """
    Convert PDF pages to PIL Images
    
    Args:
        pdf_path: Path to PDF file
        dpi: Resolution for conversion (default 300)
    
    Returns:
        List of PIL Image objects, one per page
    """
    try:
        # Try using pdf2image (requires poppler)
        from pdf2image import convert_from_path
        
        # Get poppler path if on Windows
        poppler_path = os.getenv("POPPLER_PATH")
        
        if poppler_path and os.path.exists(poppler_path):
            images = convert_from_path(
                pdf_path,
                dpi=dpi,
                poppler_path=poppler_path
            )
        else:
            # Try without poppler_path (works on Linux/Mac)
            images = convert_from_path(pdf_path, dpi=dpi)
        
        return images
        
    except ImportError:
        raise ImportError(
            "pdf2image not installed. Install with: pip install pdf2image\n"
            "Also requires poppler: https://github.com/oschwartz10612/poppler-windows/releases/"
        )
    except Exception as e:
        raise Exception(f"Failed to convert PDF to images: {e}")
