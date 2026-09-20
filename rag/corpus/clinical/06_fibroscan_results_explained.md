# Understanding FibroScan (Transient Elastography) Results — Plain Language

Source: Memorial Sloan Kettering patient education page (mskcc.org/cancer-care/patient-education/understanding-your-fibroscan-results), condensed for MedAgent RAG index. This is the primary source grounding the app's explanation of imaging-report text for FibroScan, per the plan's safety boundary: the app explains the *written* kPa number/conclusion from a report, never interprets a raw scan image.

## What kPa measures

Liver stiffness, measured in kilopascals (kPa) — higher stiffness generally means more scarring (fibrosis). Normal results are usually between 2 and 7 kPa; the scale's highest possible result is 75 kPa.

## Fibrosis stages (F0-F4)

- **F0-F1 (minimal/no scarring)**: no or mild scarring.
- **F2 (moderate)**: scarring present but potentially reversible with treatment of the underlying cause.
- **F3 (severe)**: significant scarring, still potentially reversible.
- **F4 (cirrhosis)**: advanced scarring. The Kazakhstan protocol (`02_kz_protocol_cirrhosis.md`) cites a specific cutoff of >12.4 kPa as indicating F4/cirrhosis by METAVIR staging, ~95.5% accuracy — this is the numeric threshold to use when explaining a KZ-sourced FibroScan report.

## CAP score (steatosis)

A separate score, in dB/m, measuring fat accumulation in the liver (not fibrosis directly). A CAP score of 275 dB/m or higher generally indicates significant hepatic steatosis (fatty liver).

## Important caveats for explanation

- Exact kPa cutoffs vary somewhat by the underlying disease (PBC/autoimmune vs. viral vs. fatty liver) — the app should present the Kazakhstan-protocol cutoff as the reference used, while noting that the treating physician's interpretation of her specific case is the one that matters.
- A result can be falsely elevated by recent liver inflammation or a non-fasting state — a single value should be explained in the context of the trend, same principle as lab markers.

## Application notes for MedAgent

Feeds `ocr/vision_extract.py`'s narrative-document path (a FibroScan report's typed kPa/CAP values) and `generate_explanation_node`/`followup_chat` when explaining imaging results. Reinforces the firm rule stated in the plan: only the report's written numbers/conclusion are processed, never a raw ultrasound/elastogram image.
