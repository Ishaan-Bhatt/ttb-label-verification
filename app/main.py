"""HTTP API and static web UI.

Uploads are processed in memory and never written to disk or logged.
"""

import shutil
from pathlib import Path

import pytesseract
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ocr import ImageError
from .verify import verify_label

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
SAMPLES_DIR = ROOT / "samples"

MAX_UPLOAD_BYTES = 15 * 1024 * 1024

app = FastAPI(title="Label Verification", docs_url="/api/docs", redoc_url=None)


@app.get("/api/health")
def health():
    return {"status": "ok", "ocr_engine_installed": shutil.which("tesseract") is not None}


# A plain `def` endpoint runs in FastAPI's thread pool, so a batch of uploads
# from the browser is processed in parallel.
@app.post("/api/verify")
def verify(
    image: UploadFile = File(...),
    brand_name: str = Form(""),
    class_type: str = Form(""),
    alcohol_content: str = Form(""),
    net_contents: str = Form(""),
    bottler: str = Form(""),
    country_of_origin: str = Form(""),
):
    data = image.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "This image is larger than 15 MB. Please upload a smaller file.")
    try:
        result = verify_label(
            data,
            {
                "brand_name": brand_name,
                "class_type": class_type,
                "alcohol_content": alcohol_content,
                "net_contents": net_contents,
                "bottler": bottler,
                "country_of_origin": country_of_origin,
            },
        )
    except ImageError as exc:
        raise HTTPException(422, str(exc)) from exc
    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(503, "The text-reading engine isn't installed on this server.") from exc
    return result.to_dict()


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if SAMPLES_DIR.is_dir():
    app.mount("/samples", StaticFiles(directory=SAMPLES_DIR), name="samples")
