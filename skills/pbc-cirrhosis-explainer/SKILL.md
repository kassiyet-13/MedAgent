---
name: pbc-cirrhosis-explainer
description: Use this skill whenever generating a patient-facing explanation of lab results, trends, or historical medical documents for a person with primary biliary cholangitis (PBC) / cirrhosis, especially when the output must be bilingual Kazakh+Russian, must use an encouraging tone for improving results or a supportive/actionable tone for declining results, or must include the mandatory "not a diagnosis" escalation disclaimer. Trigger this skill for the main lab-explanation generation step and for follow-up questions about the patient's history -- do NOT trigger it for internal/deterministic steps like extraction, trend computation, or severity classification, which must stay rule-based and never pass through this skill's persuasive/explanatory framing.
---

# PBC / Cirrhosis Lab Explainer

## Purpose

Turn structured lab values, a deterministic severity assessment, and retrieved
clinical context into a plain-language, bilingual (Kazakh + Russian) explanation
a non-medical patient and family can understand and act on -- without ever
presenting it as a diagnosis.

## When to use this skill

- Generating the main explanation after a lab panel has been extracted, confirmed
  by the patient, and assessed for severity/trend.
- Answering a follow-up question in the "ask about your history" chat.

## When NOT to use this skill

- Extraction, validation, reference-range lookup, trend computation, and severity
  classification are deterministic/rule-based (see `mcp_server/tools/trend.py`,
  `graph/nodes.py::classify_severity_node`) and must never be delegated to this
  skill or any other free-form LLM reasoning.

## How to write the explanation

1. **Load `glossary_kz_ru.md`** for consistent bilingual terminology -- every
   marker name, every recurring phrase (e.g. the disclaimer) must use the exact
   wording from the glossary, not an ad hoc translation, so the same term never
   reads differently across two reports.
2. **Load `tone_templates.md`** and pick the template matching the computed
   `severity`/`escalation_level` passed in by the graph (never decide the tone
   yourself from the raw numbers -- that decision was already made deterministically
   upstream).
3. Write TWO full versions, Russian first then Kazakh, each independently complete
   (not a translation of the other sentence-by-sentence -- natural phrasing in
   each language).
4. Ground every specific claim (a value, a trend direction, a recommendation) in
   the extracted values or the retrieved clinical context passed into the prompt.
   Never state a fact that isn't supported by that input.
5. **Comorbidity boundary**: if the patient's history contains non-liver findings
   (cardiac, renal, orthopedic, etc. -- confirmed present in the real discharge
   summary this app was built against), never comment on, explain, or give
   recommendations about them. Acknowledge their existence at most in passing if
   directly relevant to a question asked, and redirect to "discuss with your
   doctor" for anything outside the liver/PBC scope.
6. Always end with the disclaimer sentence from `tone_templates.md`, in both
   languages verbatim -- this is enforced a second time, independently, by
   `disclaimer_check_node` in the graph, which will append it if missing, but the
   skill should produce it correctly on its own.

## Files in this skill

- `glossary_kz_ru.md` -- fixed marker names and recurring phrases in RU/KZ.
- `tone_templates.md` -- structure templates for the four severity states
  (critical / worsening / improving / stable) plus the disclaimer text.
