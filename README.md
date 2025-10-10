# AI-Powered Notes → Mindmap & Flowchart (Flask + Vanilla JS)

Upload handwritten/printed notes (images or PDFs). The app:
- Extracts text (Tesseract OCR)
- Finds key concepts (spaCy) and relationships
- Builds interactive mindmap + flowchart (vis-network)

## Windows 11 Setup

1) System dependencies
- Tesseract OCR:
  - Install from UB Mannheim builds
  - Set env var `TESSERACT_CMD` to e.g. `C:\Program Files\Tesseract-OCR\tesseract.exe`
- Poppler (PDF to image):
  - Install Windows build
  - Set env var `POPPLER_PATH` to Poppler `bin` directory, e.g. `C:\poppler-24.02.0\Library\bin`

2) Python
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm

## Google Cloud Vision setup (recommended for messy handwriting)
1. Enable Cloud Vision API in your GCP project.
2. Create a service account with role “Vision AI User”, download its JSON key.
3. Set env var `GOOGLE_APPLICATION_CREDENTIALS` to that JSON path (Windows PowerShell):
   - `$env:GOOGLE_APPLICATION_CREDENTIALS="C:\keys\vision-key.json"`
   - Or persist: `setx GOOGLE_APPLICATION_CREDENTIALS "C:\keys\vision-key.json"` then restart terminal.
4. Install deps: `pip install -r requirements.txt`

Notes:
- Using Vision API incurs cost. Check pricing: https://cloud.google.com/vision/pricing
- PDFs are converted to images locally (no GCS needed).