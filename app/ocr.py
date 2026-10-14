"""Image loading, cleanup and text extraction with Tesseract (runs locally, no network)."""

import io
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

# Tesseract reads best when body text is roughly 20-40px tall. Labels arrive as
# anything from thumbnails to 12MP phone photos, so normalize the long side.
MIN_LONG_SIDE = 1400
MAX_LONG_SIDE = 2400
TESSERACT_CONFIG = "--oem 1 --psm 3"


class ImageError(ValueError):
    """The upload could not be used as a label image. The message is shown to the user."""


@dataclass
class Word:
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float
    line_id: tuple[int, int, int]  # (block, paragraph, line) from Tesseract


@dataclass
class OcrResult:
    words: list[Word]
    gray: np.ndarray  # the preprocessed image the boxes refer to

    @property
    def text(self) -> str:
        lines: list[list[str]] = []
        current = None
        for word in self.words:
            if word.line_id != current:
                lines.append([])
                current = word.line_id
            lines[-1].append(word.text)
        return "\n".join(" ".join(line) for line in lines)


def load_image(data: bytes) -> np.ndarray:
    """Decode an upload into a grayscale array, honoring phone-camera rotation."""
    if not data:
        raise ImageError("The file is empty.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageError("This file isn't an image we can open. Please upload a JPG or PNG.") from exc

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, "white")
        img = Image.alpha_composite(background, img)
    return np.array(img.convert("L"))


def preprocess(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    long_side = max(h, w)
    if long_side < 200:
        raise ImageError("This image is too small to read. Please upload a larger image of the label.")

    scale = 1.0
    if long_side > MAX_LONG_SIDE:
        scale = MAX_LONG_SIDE / long_side
    elif long_side < MIN_LONG_SIDE:
        scale = MIN_LONG_SIDE / long_side
    if scale != 1.0:
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=interp)

    # Light text on a dark label: flip so text is dark, which both Tesseract and
    # the bold-type measurement expect.
    if np.median(gray) < 110:
        gray = 255 - gray
    return gray


def run_ocr(gray: np.ndarray) -> OcrResult:
    data = pytesseract.image_to_data(
        gray, lang="eng", config=TESSERACT_CONFIG, output_type=pytesseract.Output.DICT
    )
    words = []
    for i, raw in enumerate(data["text"]):
        text = raw.strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        words.append(
            Word(
                text=text,
                left=data["left"][i],
                top=data["top"][i],
                width=data["width"][i],
                height=data["height"][i],
                conf=conf,
                line_id=(data["block_num"][i], data["par_num"][i], data["line_num"][i]),
            )
        )
    return OcrResult(words=words, gray=gray)


def read_label(data: bytes) -> OcrResult:
    return run_ocr(preprocess(load_image(data)))
