"""OCR + text extraction.

Digital PDF -> PyMuPDF text layer first (fast, exact).
Scanned PDF / image -> render page to image, Tesseract OCR.
If Tesseract is absent the job fails cleanly with a clear error
(status=failed, error_message names the missing binary) instead of
crashing or inventing text. Poor-quality images get grayscale +
contrast preprocessing before OCR.
"""
import io, shutil
from pathlib import Path
import fitz  # PyMuPDF

TESSERACT = shutil.which("tesseract")

def pdf_text_layer(path: Path):
    """Return (text, page_count, pages_with_text)."""
    doc = fitz.open(path)
    pages, texts = [], []
    for page in doc:
        t = page.get_text().strip()
        texts.append(t)
        pages.append(bool(t))
    return "\n\f\n".join(texts), len(doc), sum(pages)

def _rapidocr_text(data: bytes) -> str:
    """Fallback OCR when Tesseract is absent (rapidocr-onnxruntime)."""
    from rapidocr_onnxruntime import RapidOCR
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    engine = RapidOCR()
    result, _ = engine(np.array(img))
    if not result:
        return ""
    return "\n".join(line[1] for line in result)

def ocr_image_bytes(data: bytes) -> str:
    from PIL import Image, ImageEnhance, ImageOps
    if TESSERACT:
        import pytesseract
        img = Image.open(io.BytesIO(data)).convert("L")
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(1.5)
        # Upscale small images: Tesseract accuracy collapses below ~300 dpi
        if max(img.size) < 1500:
            img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        return pytesseract.image_to_string(img)
    try:
        return _rapidocr_text(data)
    except ImportError:
        raise RuntimeError("No OCR engine available: install Tesseract "
                           "(apt install tesseract-ocr) or rapidocr-onnxruntime "
                           "(pip install rapidocr-onnxruntime). Scanned documents cannot be read.")

def ocr_pdf(path: Path) -> str:
    doc = fitz.open(path)
    out = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        out.append(ocr_image_bytes(pix.tobytes("png")))
    return "\n\f\n".join(out)

def extract_text(path: Path, mime: str = ""):
    """-> (text, ocr_used: bool, page_count, detail). Raises ValueError on corrupt files."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            text, pages, with_text = pdf_text_layer(path)
            if with_text >= max(1, pages // 2):
                return text, False, pages, "digital-pdf text layer"
            # Mostly scanned: OCR every page
            return ocr_pdf(path), True, pages, "scanned-pdf OCR (300dpi)"
        if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            return ocr_image_bytes(path.read_bytes()), True, 1, "image OCR"
        raise ValueError(f"extract_text called for non-text file {suffix}")
    except Exception as e:
        # fitz raises on corrupt PDFs; surface as a clean failure, not a traceback leak
        if isinstance(e, (RuntimeError, ValueError)):
            raise
        raise ValueError(f"Could not read file ({suffix}): {e}") from e
