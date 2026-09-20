"""
One-off helper (not part of the app) to run the real extraction functions
on every file in data/sample_documents/ and save a human-readable .md file
per document into data/extraction_review/ (gitignored), so the results can
be opened side-by-side with the original image/PDF for manual review.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from ocr.vision_extract import extract_lab_panel, extract_narrative

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "data" / "sample_documents"
OUT_DIR = ROOT / "data" / "extraction_review"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def render_lab(result, source_name: str) -> str:
    lines = [f"# Lab panel extraction: {source_name}", ""]
    lines.append(f"- Overall confidence: {result.overall_confidence}")
    lines.append(f"- Possible injection detected: {result.possible_injection_detected}")
    lines.append(f"- Document date: {result.document_date}")
    lines.append(f"- Lab name: {result.lab_name}")
    lines.append("")
    lines.append("| Marker (as written) | Code | Value | Unit | Lab ref range | Flag | Notes |")
    lines.append("|---|---|---|---|---|---|---|")
    for v in result.values:
        ref = f"{v.lab_ref_low}-{v.lab_ref_high}" if v.lab_ref_low is not None else ""
        lines.append(
            f"| {v.marker_name_as_written} | {v.marker_code or ''} | {v.value} | {v.unit or ''} | {ref} | {v.lab_flag or ''} | {v.notes or ''} |"
        )
    return "\n".join(lines)


def render_narrative(result, source_name: str) -> str:
    lines = [f"# Narrative extraction: {source_name}", ""]
    lines.append(f"- Document kind: {result.document_kind}")
    lines.append(f"- Document date: {result.document_date}")
    lines.append(f"- Possible injection detected: {result.possible_injection_detected}")
    lines.append("")
    lines.append("## Extracted text")
    lines.append("")
    lines.append(result.text)
    return "\n".join(lines)


def main():
    files = sorted(SAMPLE_DIR.glob("*"))
    files = [f for f in files if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".pdf")]

    for f in files:
        name = f.name.lower()
        out_path = OUT_DIR / (f.stem + "_extracted.md")
        print(f"Processing {f.name} ...")
        try:
            if "lab" in name or "анализ" in name:
                result = extract_lab_panel(f, provider="claude")
                out_path.write_text(render_lab(result, f.name), encoding="utf-8")
            else:
                result = extract_narrative(f, provider="claude")
                out_path.write_text(render_narrative(result, f.name), encoding="utf-8")
            print(f"  -> saved {out_path}")
        except Exception as e:
            print(f"  -> ERROR: {e}")
            out_path.write_text(f"ERROR extracting {f.name}: {e}", encoding="utf-8")


if __name__ == "__main__":
    main()
