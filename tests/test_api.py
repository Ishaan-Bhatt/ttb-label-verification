"""End-to-end through the HTTP API with real OCR. Skipped where Tesseract isn't installed."""

import csv
import io
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
client = TestClient(app)
needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract not installed")


def sample_rows():
    with open(SAMPLES / "applications.csv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def expected_verdict(notes: str) -> str:
    return re.search(r"Expect: (\w+)", notes).group(1)


@needs_tesseract
@pytest.mark.parametrize("row", sample_rows(), ids=lambda r: r["filename"])
def test_sample_label_verdicts(row):
    with open(SAMPLES / row["filename"], "rb") as fh:
        response = client.post(
            "/api/verify",
            files={"image": (row["filename"], fh)},
            data={k: v for k, v in row.items() if k not in ("filename", "notes")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == expected_verdict(row["notes"]), body
    assert body["elapsed_ms"] < 5000


def test_rejects_non_image():
    response = client.post("/api/verify", files={"image": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 422
    assert "isn't an image" in response.json()["detail"]


def test_rejects_empty_file():
    response = client.post("/api/verify", files={"image": ("x.png", b"", "image/png")})
    assert response.status_code == 422


@needs_tesseract
def test_blank_image_explains_no_text_found():
    buf = io.BytesIO()
    Image.new("RGB", (800, 1000), "white").save(buf, format="PNG")
    response = client.post("/api/verify", files={"image": ("blank.png", buf.getvalue(), "image/png")})
    assert response.status_code == 422
    assert "couldn't read any text" in response.json()["detail"]


def test_index_and_samples_are_served():
    assert client.get("/").status_code == 200
    assert client.get("/samples/applications.csv").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"
