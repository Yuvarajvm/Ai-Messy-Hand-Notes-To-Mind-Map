# services/preprocess.py
import cv2
import numpy as np
from PIL import Image


def pil_to_cv2(pil_img: Image.Image) -> np.ndarray:
    """Convert PIL Image to OpenCV format"""
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def cv2_to_pil(cv_img: np.ndarray) -> Image.Image:
    """Convert OpenCV image to PIL format"""
    return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))


def preprocess_for_ocr(
    img: Image.Image,
    deskew: bool = True,
    denoise: bool = True,
    binarize: bool = True,
    morph: bool = True
) -> Image.Image:
    """
    Preprocess image for better OCR results
    
    Args:
        img: PIL Image
        deskew: Correct image rotation
        denoise: Remove noise
        binarize: Convert to black/white
        morph: Apply morphological operations
    
    Returns:
        Preprocessed PIL Image
    """
    try:
        # Convert to OpenCV format
        cv_img = pil_to_cv2(img)
        
        # Convert to grayscale
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        
        # Denoise
        if denoise:
            gray = cv2.fastNlMeansDenoising(gray, h=10)
        
        # Binarize (Otsu's thresholding)
        if binarize:
            _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Deskew (straighten image)
        if deskew:
            coords = np.column_stack(np.where(gray > 0))
            if len(coords) > 0:
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = -(90 + angle)
                else:
                    angle = -angle
                
                # Only rotate if angle is significant
                if abs(angle) > 0.5:
                    (h, w) = gray.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    gray = cv2.warpAffine(
                        gray, M, (w, h),
                        flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_REPLICATE
                    )
        
        # Morphological operations (remove small noise)
        if morph:
            kernel = np.ones((1, 1), np.uint8)
            gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
            gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
        
        # Convert back to PIL
        return Image.fromarray(gray)
        
    except Exception as e:
        # If preprocessing fails, return original image
        return img
