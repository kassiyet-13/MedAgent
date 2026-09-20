# Ascites and Hepatorenal Syndrome — Key Points for Patient Explanation

Source: AASLD Practice Guidance summary (aasld.org/practice-guidelines/diagnosis-evaluation-and-management-ascites-spontaneous-bacterial-peritonitis), condensed for MedAgent RAG index. Supplemented by the more detailed Kazakhstan protocol figures in `02_kz_protocol_cirrhosis.md` (grading, diuretic dosing) since the AASLD summary page itself is high-level.

## Why ascites matters

Ascites (fluid buildup in the abdomen) is commonly the first sign that cirrhosis has moved from "compensated" to "decompensated." About 5-10% of patients with compensated cirrhosis develop ascites per year. Its onset is a significant turning point — 5-year survival drops from roughly 80% to 30% once ascites develops, which is why any new or worsening ascites should always be flagged for prompt medical attention rather than explained away.

## Major complications to watch for

- **Spontaneous bacterial peritonitis (SBP)** — infection of the ascitic fluid; can present with fever, abdominal pain, or confusion, and needs urgent care.
- **Hepatorenal syndrome (HRS)** — kidney function decline related to advanced liver disease; reflected in rising creatinine (see `mcp_server/data/reference_ranges.json`, critical threshold >250 umol/L used here, consistent with HRS Type I criteria of creatinine doubling above 220 umol/L within 2 weeks per the KZ protocol).
- **Electrolyte abnormalities**, especially low sodium — often related to diuretic use and free water handling, and is one of this app's critical-escalation triggers (sodium <125 mmol/L).
- **Nutritional imbalance**.

## Clinical recommendation for advanced cases

Patients who develop clinically significant ascites and related complications should be considered for liver transplant evaluation and, when appropriate, palliative care discussion — this is physician-led decision-making, never something MedAgent should suggest or imply on its own; the app's role is limited to flagging the relevant lab/imaging signals and encouraging a doctor visit.

## Application notes for MedAgent

This is the source for `escalate_node`'s framing when ascites-related markers (sodium, creatinine, albumin) cross critical thresholds — tone should be calm but clear that this warrants prompt medical follow-up, not alarm without direction.
