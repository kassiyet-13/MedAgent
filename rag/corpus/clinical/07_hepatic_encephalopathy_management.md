# Hepatic Encephalopathy: Grading, Triggers, and Management

Source: Cleveland Clinic patient education (my.clevelandclinic.org/health/diseases/21220-hepatic-encephalopathy) and AASLD/EASL practice guideline content on hepatic encephalopathy in chronic liver disease, condensed for MedAgent RAG index. West-Haven staging itself is already covered briefly in `02_kz_protocol_cirrhosis.md`; this file focuses on precipitating factors and day-to-day management, which that file does not cover.

## What hepatic encephalopathy is

Hepatic encephalopathy (HE; печеночная энцефалопатия) is a decline in brain function that happens when a damaged liver can no longer clear toxins — ammonia in particular — from the blood. It is one of the defining signs that cirrhosis has decompensated, alongside ascites and variceal bleeding.

## West-Haven grading (recap)

`02_kz_protocol_cirrhosis.md` already lists the five West-Haven stages (Minimal, I-IV) in detail. Two practical anchor points worth repeating here: Grade I-II is usually managed as an outpatient with medication adjustment, while Grade III-IV (marked confusion, drowsiness progressing toward unresponsiveness, or asterixis with disorientation) needs urgent medical evaluation, not home management.

## Precipitating factors

HE episodes are usually *triggered* by something correctable, not just a steady decline. Recognizing a likely trigger is itself part of the diagnostic picture. Common triggers include:

- **Gastrointestinal bleeding** (including variceal bleeding) — blood in the gut is a large protein load that raises ammonia production.
- **Infection** — including spontaneous bacterial peritonitis, urinary tract infection, or pneumonia.
- **Constipation** — slower gut transit increases toxin absorption; this is one of the most common and most fixable triggers.
- **Dehydration** — including from overly aggressive diuretic use.
- **Electrolyte imbalance**, especially low sodium or low potassium.
- **Kidney dysfunction.**
- **Medication non-adherence or sedative use** (e.g., missed lactulose doses, or new benzodiazepines/opioids).
- **Alcohol use.**

Because most episodes trace back to one of these, an HE episode is also, in effect, a prompt to check for infection, bleeding, constipation, and recent medication/diet changes — not just to increase HE medication in isolation.

## Treatment

**Lactulose** is first-line therapy. It is a synthetic, non-absorbable sugar that draws water into the bowel and is fermented by gut bacteria in a way that traps ammonia in the stool, speeding its elimination. Dosing is titrated to a clinical target — typically 2-3 soft/loose stools per day — rather than a fixed dose; both too little (undertreated HE) and too much (dehydration, electrolyte loss, which can itself trigger more HE) are problems, so ongoing titration and follow-up matter.

**Rifaximin** is a non-absorbed antibiotic that reduces ammonia-producing gut bacteria. It is typically added to lactulose — not used to replace it — for patients who have breakthrough HE episodes on lactulose alone, or for reducing the risk of recurrence after a first overt HE episode. Combination lactulose + rifaximin has more evidence for preventing recurrent hospitalizations than either agent alone.

## When to escalate

- Any new confusion, personality change, unusual drowsiness, or disorientation in a person with known cirrhosis/PBC should prompt medical contact, since it can signal either a new HE episode or an unrelated acute problem (e.g., infection, bleeding) presenting as confusion.
- Grade III-IV features (severe drowsiness, marked confusion, inability to stay awake, or coma) are a medical emergency — this is not a "wait and see if the next lactulose dose helps" situation.
- A missed or skipped lactulose regimen, new sedating medication, or several days without a bowel movement in a patient with known HE risk is worth flagging to the care team proactively, even before symptoms appear, given how often these are the actual trigger.

## Application notes for MedAgent

- This file supplies the precipitating-factor and treatment-principle content that `02_kz_protocol_cirrhosis.md`'s West-Haven table does not cover. Retrieval for an HE-related query should be able to draw on both files together.
- The app should never suggest a specific lactulose/rifaximin dose adjustment — dosing is titrated by the treating physician to a stool-frequency target. The app's role is limited to explaining what the medications do and what patterns (missed doses, constipation, new confusion) are worth mentioning to the doctor.
- Any user-reported confusion, disorientation, or "she seems different today" type observation about the patient should be treated by `escalate_node` with the same urgency register as the other critical-escalation triggers already documented in `05_ascites_hrs_aasld.md`.
