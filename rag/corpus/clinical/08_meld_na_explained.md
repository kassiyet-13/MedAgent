# Understanding the MELD-Na Score

Source: UPMC transplant patient education (upmc.com/services/transplant/patients/resources/meld-score) and the OPTN/UNOS 2016 MELD-Na policy formula, condensed for MedAgent RAG index. The formula itself is already implemented in `mcp_server/tools/trend.py` (`compute_meld_na`) — this file is the patient-facing explanation of what the resulting number *means*, not a re-derivation of the math.

## What MELD-Na is

MELD-Na (Model for End-Stage Liver Disease – Sodium) is a numeric score, from 6 to 40, originally developed to predict short-term (roughly 90-day) mortality risk in people with advanced liver disease. Because it is a good general predictor of how sick a liver-disease patient currently is, it was adopted by OPTN/UNOS as the primary tool for prioritizing deceased-donor liver transplant waitlists in the United States — the sickest patients (highest scores) are offered available organs first, alongside blood type and body size compatibility.

## What goes into it

The score is calculated from four lab values, all of which this app already tracks:

- **Bilirubin** — reflects how well the liver is clearing bile; higher values indicate worse liver excretory function.
- **INR** (derived from prothrombin time) — reflects the liver's ability to make clotting proteins; a higher INR indicates reduced synthetic function.
- **Creatinine** — reflects kidney function, which commonly declines alongside advanced liver disease (see hepatorenal syndrome in `05_ascites_hrs_aasld.md`).
- **Sodium** — added in the 2016 revision (hence "-Na"). Low sodium was found, in UNOS registry data, to independently predict higher 90-day waitlist mortality beyond what the original three-value MELD already captured.

The exact formula (logarithmic combination of these four values, with sodium applied only once the base MELD exceeds 11) is implemented in `mcp_server/tools/trend.py`, following the OPTN 2016 specification, including the standard bounding rules (creatinine capped at 1.0-4.0 mg/dL, sodium bounded 125-137 mmol/L).

## How to think about the number

- A **higher score means the liver is doing a worse job**, all else equal — this is the honest, general way to describe the direction of the number.
- The score is a *population-level* statistical predictor, not a personal prognosis for any one patient — it was built and validated to rank waitlist priority and estimate short-term risk across large cohorts, not to tell an individual patient exactly what will happen to them.
- Transplant centers typically re-check higher scores more frequently than lower ones (very high scores are reviewed weekly, low scores may only be reassessed annually) — a general illustration that the score is meant to be watched as a *trend* over time, similar to the app's other lab markers, rather than read as a one-time verdict.
- Because it directly combines four different organ systems' worth of information (liver excretion, liver synthetic function, kidney function, fluid/sodium balance), a rising MELD-Na can reflect a change in any one of its inputs — which is exactly why the app already surfaces the underlying bilirubin/INR/creatinine/sodium trend alongside the composite score (`compute_trend` in `mcp_server/tools/trend.py`), so the number is never presented without its components.

## What the app should and should not say

- The app may explain what MELD-Na is, what it's built from, and show the patient's own computed trend over time.
- The app should **never** state or imply a survival estimate, a transplant-listing recommendation, or a specific score threshold as a "danger point" for this individual patient — those are physician-led interpretations that depend on the whole clinical picture, not just the number. Any discussion of what a given score might mean for this patient's care should be explicitly framed as "a question for her treating physician/transplant team," consistent with the app's existing rule never to make transplant-referral judgments (see `02_kz_protocol_cirrhosis.md`, Transplant Referral Triggers section).

## Application notes for MedAgent

- This is the explainer text `generate_explanation_node`/`followup_chat` should draw on whenever the patient's computed `meld_na_series` (from `compute_trend`) is being described in plain language.
- Keep the framing calm and factual — describe direction of change ("this component went up/down") rather than assigning alarm language to any specific score value, matching the non-alarmist register used throughout the rest of this corpus.
