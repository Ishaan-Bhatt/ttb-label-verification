"""Generate the sample label images and matching application data in samples/.

Each label exercises one scenario from the stakeholder interviews. Run:
    python scripts/make_samples.py
"""

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.warning import STANDARD_WARNING  # noqa: E402

OUT = ROOT / "samples"

FONT_CANDIDATES = {
    "sans": ["DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "sans_bold": ["DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "serif_bold": ["DejaVuSerif-Bold.ttf", "C:/Windows/Fonts/georgiab.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"],
}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES[kind]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise SystemExit(f"No {kind} font found; tried {FONT_CANDIDATES[kind]}")


HEADING = "GOVERNMENT WARNING:"
BODY = STANDARD_WARNING[len(HEADING):].strip()


@dataclass
class Label:
    filename: str
    brand: str
    class_type: str
    alcohol: str
    net: str
    bottler: list[str]
    country: str = ""
    heading: str = HEADING
    body: str = BODY
    heading_bold: bool = True
    body_bold: bool = False
    has_warning: bool = True
    background: str = "#f6efdd"
    ink: str = "#2b1d12"
    photo: bool = False
    # Application data submitted for this label, and what the sample demonstrates.
    application: dict = field(default_factory=dict)
    notes: str = ""


OLD_TOM_APP = {
    "brand_name": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "alcohol_content": "45% Alc./Vol. (90 Proof)",
    "net_contents": "750 mL",
    "bottler": "Old Tom Distillery, Bardstown, Kentucky",
    "country_of_origin": "",
}
OLD_TOM = dict(
    brand="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol="45% Alc./Vol. (90 Proof)",
    net="750 mL",
    bottler=["Distilled and Bottled by", "Old Tom Distillery", "Bardstown, Kentucky"],
)

LABELS = [
    Label("01_old_tom_compliant.png", **OLD_TOM, application=OLD_TOM_APP,
          notes="Fully compliant label. Expect: pass."),
    Label("02_stones_throw_capitalization.png", brand="STONE'S THROW", class_type="Small Batch Gin",
          alcohol="41.5% Alc./Vol. (83 Proof)", net="700 mL",
          bottler=["Distilled by", "Stone's Throw Spirits", "Portland, Oregon"],
          background="#e8eef2", ink="#14263a",
          application={"brand_name": "Stone's Throw", "class_type": "Small Batch Gin",
                       "alcohol_content": "41.5% Alc./Vol. (83 Proof)", "net_contents": "700 mL",
                       "bottler": "Stone's Throw Spirits, Portland, Oregon", "country_of_origin": ""},
          notes="Brand in all caps on label, title case on application (Dave's example). Expect: pass."),
    Label("03_old_tom_wrong_abv.png", **{**OLD_TOM, "alcohol": "40% Alc./Vol. (80 Proof)"},
          application=OLD_TOM_APP, notes="Label says 40%, application says 45%. Expect: fail."),
    Label("04_title_case_warning.png", **OLD_TOM, heading="Government Warning:", application=OLD_TOM_APP,
          notes="Warning heading in title case (Jenny's example). Expect: fail."),
    Label("05_warning_heading_not_bold.png", **OLD_TOM, heading_bold=False, application=OLD_TOM_APP,
          notes="Warning heading in regular weight. Expect: fail."),
    Label("06_altered_warning_wording.png", **OLD_TOM,
          body=BODY.replace("women should not drink", "women should avoid drinking"),
          application=OLD_TOM_APP, notes="Warning wording changed. Expect: fail."),
    Label("07_missing_warning.png", **OLD_TOM, has_warning=False, application=OLD_TOM_APP,
          notes="No government warning. Expect: fail."),
    Label("08_wrong_net_contents.png", **{**OLD_TOM, "net": "1 L"}, application=OLD_TOM_APP,
          notes="Label says 1 L, application says 750 mL. Expect: fail."),
    Label("09_imported_wine.png", brand="CH\u00c2TEAU MARCHAND", class_type="Bordeaux Red Wine",
          alcohol="13.5% Alc./Vol.", net="750 mL",
          bottler=["Imported by", "Harbor Wine Imports", "Seattle, Washington"], country="Product of France",
          background="#f3ece6", ink="#4a0f1c",
          application={"brand_name": "Chateau Marchand", "class_type": "Bordeaux Red Wine",
                       "alcohol_content": "13.5%", "net_contents": "750 mL",
                       "bottler": "Harbor Wine Imports, Seattle, Washington", "country_of_origin": "France"},
          notes="Imported wine with country of origin; accent on label but not application. Expect: pass."),
    Label("10_old_tom_photo.jpg", **OLD_TOM, photo=True, application=OLD_TOM_APP,
          notes="Compliant label photographed at a slight angle with glare and noise. Expect: pass."),
    Label("11_whole_warning_bold.png", **OLD_TOM, body_bold=True, application=OLD_TOM_APP,
          notes="Entire warning in bold; only the heading may be bold. Expect: fail."),
]

W, H = 1200, 1600
MARGIN = 80


def wrap_runs(draw, runs, max_width):
    """Lay out (word, font) runs into lines no wider than max_width."""
    lines, line, width = [], [], 0
    for word, f in runs:
        w = draw.textlength(word + " ", font=f)
        if line and width + w > max_width:
            lines.append(line)
            line, width = [], 0
        line.append((word, f))
        width += w
    if line:
        lines.append(line)
    return lines


def centered(draw, text, f, y, fill):
    for line in wrap_runs(draw, [(w, f) for w in text.split()], W - 2 * MARGIN - 40):
        s = " ".join(w for w, _ in line)
        x = (W - draw.textlength(s, font=f)) / 2
        draw.text((x, y), s, font=f, fill=fill)
        y += int(f.size * 1.2)
    return y


def render(label: Label) -> Image.Image:
    img = Image.new("RGB", (W, H), label.background)
    d = ImageDraw.Draw(img)
    d.rectangle([30, 30, W - 30, H - 30], outline=label.ink, width=6)
    d.rectangle([44, 44, W - 44, H - 44], outline=label.ink, width=2)

    y = 120
    y = centered(d, label.brand, font("serif_bold", 92), y, label.ink) + 30
    y = centered(d, label.class_type, font("sans", 48), y, label.ink) + 40
    d.line([MARGIN + 150, y, W - MARGIN - 150, y], fill=label.ink, width=3)
    y += 50
    y = centered(d, label.alcohol, font("sans_bold", 46), y, label.ink) + 20
    y = centered(d, label.net, font("sans_bold", 46), y, label.ink) + 50
    for line in label.bottler:
        y = centered(d, line, font("sans", 34), y, label.ink) + 4
    if label.country:
        y = centered(d, label.country, font("sans", 34), y + 16, label.ink)

    if label.has_warning:
        size = 28
        body_font = font("sans_bold" if label.body_bold else "sans", size)
        head_font = font("sans_bold" if label.heading_bold else "sans", size)
        runs = [(w, head_font) for w in label.heading.split()] + [(w, body_font) for w in label.body.split()]
        lines = wrap_runs(d, runs, W - 2 * MARGIN)
        line_h = int(size * 1.35)
        wy = H - MARGIN - len(lines) * line_h
        for line in lines:
            x = MARGIN
            for word, f in line:
                d.text((x, wy), word, font=f, fill=label.ink)
                x += d.textlength(word + " ", font=f)
            wy += line_h
    return img


def photograph(img: Image.Image) -> Image.Image:
    """Make a clean render look like a quick phone photo of a bottle."""
    img = img.rotate(2.0, expand=True, fillcolor=(70, 62, 55), resample=Image.Resampling.BICUBIC)
    glare = Image.new("L", img.size, 0)
    gd = ImageDraw.Draw(glare)
    gd.ellipse([img.width * 0.55, img.height * 0.08, img.width * 0.95, img.height * 0.38], fill=110)
    glare = glare.filter(ImageFilter.GaussianBlur(80))
    img = Image.composite(Image.new("RGB", img.size, "white"), img, glare)
    img = img.filter(ImageFilter.GaussianBlur(1.1))
    noise = Image.effect_noise(img.size, 18).convert("RGB")
    img = Image.blend(img, noise, 0.06)
    return img.resize((int(img.width * 0.85), int(img.height * 0.85)), Image.Resampling.LANCZOS)


def main():
    OUT.mkdir(exist_ok=True)
    for label in LABELS:
        img = render(label)
        if label.photo:
            photograph(img).save(OUT / label.filename, quality=72)
        else:
            img.save(OUT / label.filename)

    columns = ["filename", "brand_name", "class_type", "alcohol_content", "net_contents",
               "bottler", "country_of_origin", "notes"]
    with open(OUT / "applications.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for label in LABELS:
            writer.writerow({"filename": label.filename, **label.application, "notes": label.notes})
    print(f"Wrote {len(LABELS)} labels to {OUT}")


if __name__ == "__main__":
    main()
