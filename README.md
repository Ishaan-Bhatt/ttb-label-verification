# Label Verification Prototype

A web app that checks an alcohol label image against its application data: brand name, class/type, alcohol content, net contents, bottler name and address, country of origin, and the Government Health Warning Statement.

**Live demo:** https://ttb-label-verification.happycliff-476a8415.northcentralus.azurecontainerapps.io/

The page has built-in examples, so you can try it without any files: on **Check one label**, pick from **"Or try an example label"**; on **Check many labels**, press **Try the example batch**.

---

## Running it

### With Docker (recommended)

```bash
docker build -t label-verify .
docker run -p 8000:8000 label-verify
```

Open http://localhost:8000.

### Without Docker

You need Python 3.12 and [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) on your `PATH` (`apt install tesseract-ocr`, `brew install tesseract`, or the [Windows installer](https://github.com/UB-Mannheim/tesseract/wiki)).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

### Tests

```bash
pytest
```

There are 42 tests. The unit tests cover the matching rules. The end-to-end tests send every sample label through the HTTP API with real OCR and check that each gets its expected verdict in under 5 seconds. The end-to-end tests skip themselves if Tesseract isn't installed. To run everything inside the container:

```bash
docker run --rm -v "$PWD:/srv" label-verify sh -c "pip install -q pytest httpx && pytest"
```

### Deploying

The app is one Docker container with no external services, so it runs on any container host. The live demo runs on **Azure Container Apps**, the same cloud the agency uses. One replica is kept running at all times (`--min-replicas 1`), so there's no cold-start delay. The image is built locally and pulled from GitHub Container Registry:

```powershell
# Build and publish the image (make the package public in GitHub's package settings)
docker build --platform linux/amd64 -t ghcr.io/ishaan-bhatt/ttb-label-verification:v1 .
docker push ghcr.io/ishaan-bhatt/ttb-label-verification:v1

# One-time setup (use a region your subscription allows)
az group create --name ttb-label-rg --location northcentralus
az containerapp env create --name ttb-label-env --resource-group ttb-label-rg `
  --location northcentralus --logs-destination none

az containerapp create --name ttb-label-verification --resource-group ttb-label-rg `
  --environment ttb-label-env --image ghcr.io/ishaan-bhatt/ttb-label-verification:v1 `
  --target-port 8000 --ingress external --cpu 1 --memory 2Gi --min-replicas 1 --max-replicas 2

# Ship a new version
az containerapp update -n ttb-label-verification -g ttb-label-rg `
  --image ghcr.io/ishaan-bhatt/ttb-label-verification:v2
```

---

## How to use it

**One label:** upload the label image, type in what the application says, and press **Check label**. Any box left empty is skipped. The government warning is always checked.

**Many labels:** select all the label images, plus a CSV with one row per label. The `filename` column must match the image file names; there's a downloadable template on the page:

```csv
filename,brand_name,class_type,alcohol_content,net_contents,bottler,country_of_origin
label_001.jpg,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45% Alc./Vol. (90 Proof),750 mL,"Old Tom Distillery, Bardstown, Kentucky",
```

Results show up as each label finishes. You can filter them to *Problems / Needs review / Passed*, click any row for the full breakdown, and download all results as a CSV.

Every result is one of three outcomes:

| Result | Meaning |
|---|---|
| ✓ **Match / Passed** | The label agrees with the application. |
| ⚠ **Review** | Probably fine, but the tool isn't certain. An agent should take a quick look. The screen shows exactly what to compare. |
| ✗ **Mismatch / Problems found** | The label disagrees with the application or breaks the warning rules. |

---

## Approach

### Why local OCR, not a cloud AI API

Marcus (IT) said the agency firewall blocks outbound traffic to many domains, and that the last vendor pilot partly failed because its ML endpoints were blocked. Sarah said results need to come back in about 5 seconds or agents won't use the tool.

So the app reads labels with **Tesseract**, an open-source neural-network OCR engine, running **inside the container**. Images never leave the server and no API keys are needed. Nothing the firewall blocks can break it, and cost doesn't grow with the number of labels. It takes about **0.5–0.8 s per label**, and about **1.2 s each when processing a batch four at a time** (100 labels in 30 s, measured locally).

The extracted text then goes through **deterministic rules** instead of a language model. For a compliance tool that matters: the same label always gets the same answer, and every answer can be explained ("label shows 40%, application says 45%").

### The checks

The two key checks need opposite levels of strictness. Dave wants judgment on brand names, while Jenny says the warning must be exact.

| Field | Rule |
|---|---|
| Brand name, class/type, country | Must contain the same words. Capitalization, punctuation and accents are ignored, so `STONE'S THROW` = `Stone's Throw` and `CHÂTEAU` = `Chateau`, and the result notes the difference. A near-miss such as one letter off goes to **Review**, showing what the label says. |
| Alcohol content | Compared as numbers: `45%` = `45 % Alc/Vol`. If the application gives proof, the proof on the label must match too. When a label has several percentages (e.g. "100% corn"), the one next to "Alc."/"Vol." is used. |
| Net contents | Compared as volumes with unit conversion: `750 mL` = `75 cl` ≈ `25.4 fl oz` (1% tolerance). |
| Bottler name and address | Checked word by word, because addresses wrap across lines and get reformatted. Missing or misspelled words are listed by name. |
| **Government warning** | Four sub-checks, based on 27 CFR 16.21–16.22: **(1)** present; **(2)** heading reads exactly `GOVERNMENT WARNING:` in capitals (title case fails); **(3)** heading is bold and the rest of the statement is *not* bold (16.22 forbids that too); **(4)** wording matches the statutory text word for word, with every difference shown side by side (required vs. on the label). |

**Telling OCR misreads from real wording changes.** OCR sometimes misreads a letter, e.g. `pregnancv` for `pregnancy`. If the only differences are up to three words that are each one or two characters off, the result is **Review**, not a fail, and the differing words are shown. Anything larger, such as a changed phrase, a dropped clause or added words, is a **Mismatch**.

**Bold detection.** OCR returns text, not font weight. So the app measures stroke thickness from the pixels: for a run of ink, width ≈ 2 × area ÷ perimeter. It then compares the heading with words from the same paragraph in the same image, so blur, resolution and font size affect both sides equally. On the samples (clean, photographed, and half resolution), a bold heading measured 1.4–2.1× thicker than the body and a regular heading 1.05–1.15×. The thresholds are: ≥ 1.3 is bold, ≤ 1.2 is not bold, and anything between goes to **Review**.

### Usability

The interviews said the tool must be usable by someone like "my mother… 73", and that half the team is over 50. So:

- 18 px base text, high contrast, large buttons.
- Two clearly labeled tabs and numbered steps.
- Every status shown with an icon and a word, never color alone.
- One clear verdict at the top of each result, with failing rows highlighted.
- Plain-English error messages ("This file isn't an image we can open…").
- No external fonts, scripts or CDNs, so the page itself can't be broken by the firewall.
- Works at phone width.

### Data handling

Uploads are processed in memory and never written to disk, logged, or sent anywhere. Nothing is stored between requests.

---

## Sample labels

`samples/` holds 11 generated labels and `applications.csv`, which maps each one to its application data and expected verdict. Regenerate them with `python scripts/make_samples.py`. Run them all with `python scripts/check_samples.py`.

| Sample | Scenario | Result |
|---|---|---|
| 01 | Compliant bourbon label (the README example) | Pass |
| 02 | `STONE'S THROW` on label, `Stone's Throw` on application | Pass |
| 03 | Label 40% / 80 proof, application 45% / 90 proof | Fail |
| 04 | `Government Warning:` in title case | Fail |
| 05 | Warning heading not bold | Fail |
| 06 | Warning reworded ("should avoid drinking") | Fail |
| 07 | No warning | Fail |
| 08 | Label 1 L, application 750 mL | Fail |
| 09 | Imported wine, `Product of France`, accented brand | Pass |
| 10 | Compliant label shot as a phone photo: tilted, glare, blur, noise, JPEG | Pass |
| 11 | Whole warning in bold | Fail |

---

## Assumptions

- **The agent supplies the application data.** It's typed into the form or provided as a CSV. There is no COLA integration, per Marcus: it's a standalone proof of concept.
- **Empty application fields are skipped.** Required fields differ by beverage type (e.g. some wines and beers don't need alcohol content), so the agent decides what to check. The warning is always checked because it's required on every alcohol beverage.
- **Warning wording is compared word for word, ignoring punctuation and the case of the body text.** The heading's capitalization is checked strictly. Punctuation inside the body is left out because OCR misreads small commas and periods too often for a strict check to be useful.
- **Each label is a single image.** A label spread across front and back images would need to be merged first.

## Limitations and trade-offs

- **Hard photos.** Tilted, glared and blurry photos are handled (sample 10). Curved text on a round bottle, heavy perspective, script fonts and very low resolution can still defeat OCR. In those cases the app returns **Review** or says it couldn't read the text; it doesn't guess. Jenny flagged this area as out of scope for the prototype.
- **Bold detection is an estimate.** It's calibrated on the sample labels. Unusual typefaces could land in the "unsure" band, which goes to **Review**, not to a false pass or fail.
- **Minimum type size** (16.22(b), e.g. 2 mm on a 750 mL bottle) isn't checked, because physical size can't be known from pixels without the image's scale.
- **No login, audit trail or storage.** These are out of scope for a prototype; a production version would need them.
- **Batch size.** A batch runs from the browser, so the tab has to stay open. A 300-label batch takes about 1.5 minutes on one small server.

## What I'd do next

1. **An optional vision-model reader for hard images.** The OCR step is isolated in `app/ocr.py`. When OCR confidence is low, the app could fall back to a vision model. The agency already runs on Azure, so that could be Azure AI Vision, or Claude through Microsoft Foundry, subject to the agency's authorization process. Clean labels would stay on the fast local path.
2. **Pre-filled checks by beverage type.** Spirits, wine and beer have different required fields.
3. **Deskewing and perspective correction** for photos.
4. **Evaluation on real COLA label images** to tune the thresholds beyond the generated samples.

---

## Project layout

```
app/
  main.py        HTTP API (FastAPI) and static file serving
  verify.py      runs all checks for one label and produces the verdict
  ocr.py         image loading, cleanup and Tesseract text extraction
  fields.py      brand / class / alcohol / net contents / address / country checks
  warning.py     government warning checks (presence, caps, wording, bold)
  bold.py        stroke-thickness measurement for bold detection
  text.py        normalization and fuzzy phrase search
  models.py      result types
  static/        the web page (plain HTML/CSS/JS, no build step)
samples/         generated test labels + applications.csv
scripts/         sample generator and a runner that checks every sample
tests/           unit and end-to-end tests
```

**Tools:** Python 3.12, FastAPI, Tesseract 5 (via pytesseract), OpenCV, Pillow, RapidFuzz, pytest; vanilla HTML/CSS/JavaScript.
