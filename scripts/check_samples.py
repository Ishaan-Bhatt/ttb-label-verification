"""Run every sample label through the verifier and print a summary.

    python scripts/check_samples.py [-v]
"""

import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import bold  # noqa: E402
from app.ocr import read_label  # noqa: E402
from app.verify import check_application  # noqa: E402
from app.warning import _find_heading  # noqa: E402

verbose = "-v" in sys.argv

with open(ROOT / "samples" / "applications.csv", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))

for row in rows:
    t0 = time.perf_counter()
    ocr = read_label((ROOT / "samples" / row["filename"]).read_bytes())
    result = check_application(ocr, row)
    ms = (time.perf_counter() - t0) * 1000
    print(f"{row['filename']:<38} {result.verdict:<7} {ms:6.0f} ms  | {row['notes']}")
    for c in result.fields + result.warning.checks:
        if c.status.value != "not_checked" and (verbose or c.status.value != "match"):
            print(f"    {c.status.value:<9} {c.label}: {c.message} [found: {c.found}]")
    for d in result.warning.differences:
        print(f"    diff: expected '{d.expected}' / found '{d.found}'")
    if verbose:
        heading = _find_heading(ocr.words)
        if heading:
            hw = ocr.words[heading[0] : heading[0] + heading[1]]
            ref = [w for w in ocr.words[heading[0] + heading[1] :] if bold.is_cap_height_word(w.text)][:40]
            print(f"    bold (stroke px, height px): heading={bold.measure(ocr.gray, hw)} body={bold.measure(ocr.gray, ref)}")
        print("    ocr:", ocr.text.replace("\n", " | ")[:400])
