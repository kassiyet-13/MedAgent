"""
Day-1 de-risk script (not the final OCR module).
Sends real sample documents through Claude vision and GPT-4o vision with a
draft extraction prompt to check whether the vision-LLM-OCR approach holds
before building the real graph/nodes around it.

Extraction prompts explicitly instruct the models to omit patient-identifying
info (name, DOB, ID number, address) from their output, even though visible
in the source image -- this is a prompt-level precaution for this manual
test only, NOT a substitute for the real Presidio-based guardrails/pii_scrub.py
pipeline planned for Day 4.
"""
import base64
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import anthropic
import fitz  # pymupdf
from openai import OpenAI

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_documents"
CLAUDE_MODEL = "claude-sonnet-5"
OPENAI_MODEL = "gpt-4o"

LAB_PROMPT = """You are looking at a photo of a clinical lab report (possibly in Russian or Kazakh).
Extract every lab marker you can find as JSON: a list of objects with fields
marker_name_as_written, value, unit, lab_reference_range_as_written (if shown).
Do NOT include the patient's name, date of birth, ID/IIN number, address, or the
ordering doctor's name in your output, even if visible in the image -- omit those
fields entirely. If the image is blurry or a field is unreadable, set the value to
null and add a "notes" field explaining what's uncertain. Respond with JSON only."""

NARRATIVE_PROMPT = """You are looking at a photo/scan of a medical document (discharge summary,
ultrasound report, or FibroScan report), possibly in Russian or Kazakh.
Transcribe the clinically relevant text (diagnosis, findings, conclusion, measurements,
medications, dates of the medical events) as plain text.
Do NOT include the patient's full name, date of birth, ID/IIN number, home address,
or phone number in your output -- omit those, replace with [PATIENT] if needed for
readability. Note the document date if visible."""


def encode_image(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    ext = path.suffix.lower().lstrip(".")
    media_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    return base64.standard_b64encode(data).decode("utf-8"), media_type


def pdf_first_page_to_png_bytes(path: Path) -> bytes:
    doc = fitz.open(path)
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=200)
    return pix.tobytes("png")


def call_claude(prompt: str, image_b64: str, media_type: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def call_gpt4o(prompt: str, image_b64: str, media_type: str) -> str:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}},
                ],
            }
        ],
    )
    return resp.choices[0].message.content


def run_on_image(path: Path, prompt: str, label: str):
    print(f"\n{'='*70}\n{label}: {path.name}\n{'='*70}")
    img_b64, media_type = encode_image(path)

    print("\n--- Claude Sonnet ---")
    try:
        print(call_claude(prompt, img_b64, media_type))
    except Exception as e:
        print(f"[ERROR] {e}")

    print("\n--- GPT-4o ---")
    try:
        print(call_gpt4o(prompt, img_b64, media_type))
    except Exception as e:
        print(f"[ERROR] {e}")


def run_on_pdf(path: Path, prompt: str, label: str):
    print(f"\n{'='*70}\n{label}: {path.name} (first page, rasterized)\n{'='*70}")
    png_bytes = pdf_first_page_to_png_bytes(path)
    img_b64 = base64.standard_b64encode(png_bytes).decode("utf-8")
    media_type = "image/png"

    print("\n--- Claude Sonnet (native PDF input) ---")
    try:
        pdf_b64 = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        print("".join(block.text for block in resp.content if block.type == "text"))
    except Exception as e:
        print(f"[ERROR] {e}")

    print("\n--- GPT-4o (rasterized first page) ---")
    try:
        print(call_gpt4o(prompt, img_b64, media_type))
    except Exception as e:
        print(f"[ERROR] {e}")


if __name__ == "__main__":
    # First de-risk pass: one representative file per document type (not all 5 lab
    # pages) to keep this quick/cheap. Pass --all as argv to run every file.
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        files = sorted(SAMPLE_DIR.glob("*"))
        files = [f for f in files if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".pdf")]
    else:
        names = ["lab_2024_12.jpeg", "узи.jpeg", "fibroscan.jpeg", "vipiska1.pdf"]
        files = [SAMPLE_DIR / n for n in names if (SAMPLE_DIR / n).exists()]
    if not files:
        print(f"No sample files found in {SAMPLE_DIR}")
        sys.exit(1)

    for f in files:
        name = f.name.lower()
        if "lab" in name or "анализ" in name:
            run_on_image(f, LAB_PROMPT, "LAB PANEL")
        elif f.suffix.lower() == ".pdf":
            run_on_pdf(f, NARRATIVE_PROMPT, "NARRATIVE DOC (PDF)")
        else:
            run_on_image(f, NARRATIVE_PROMPT, "NARRATIVE/IMAGING DOC")
