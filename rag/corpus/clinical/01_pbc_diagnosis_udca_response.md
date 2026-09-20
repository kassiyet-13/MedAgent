# Primary Biliary Cholangitis: Diagnosis and UDCA Treatment Response Criteria

Source: APASL clinical practice guidance summary (PMC8843914), condensed for MedAgent RAG index.

## Diagnosis Criteria

PBC diagnosis requires meeting two or more of three criteria:

1. **Biochemical evidence**: elevation of ALP and GGT with extrahepatic biliary obstruction excluded by imaging.
2. **Immunological markers**: presence of AMA (anti-mitochondrial antibody) or other PBC-specific ANAs including anti-sp100 or anti-gp210.
   - AMA-M2 subtype: >90-95% sensitivity and specificity for PBC.
   - Anti-gp210 and anti-sp100: low sensitivity (15-40%) but high specificity (>95%), useful for AMA-negative cases.
3. **Histological evidence**: non-suppurative destructive cholangitis mainly affecting the interlobular bile ducts (biopsy, not always needed if criteria 1+2 are met).

## UDCA (Ursodeoxycholic Acid) Treatment

Standard dosing: 13-15 mg/kg per day, single or divided oral doses. Lower doses (5-7 mg/kg) are less effective; higher doses (23-25 mg/kg) provide no additional benefit.

## Biochemical Response Assessment

Response to UDCA is assessed at 6-12 months using one of several validated criteria:

| Criteria | Timeline | Definition |
|---|---|---|
| Paris-II | 12 months | ALP and AST <= 1.5x ULN, AND normalization of bilirubin |
| Toronto | 24 months | ALP <= 1.67x ULN |
| GLOBE Score | 12 months | Composite: age, ALP, bilirubin, albumin, platelet count |
| UK-PBC Score | 12 months | Baseline albumin/platelets plus 12-month labs |

ALP and total bilirubin are the two most important variables in evaluating UDCA response.

## Monitoring Recommendations

- Assess biochemical response at 6 or 12 months after starting UDCA.
- 30-40% of patients show an insufficient response and may need second-line agents (e.g. obeticholic acid) — this decision belongs to the treating physician, never to be suggested as a conclusion by this app.
- Treatment adherence matters — roughly 11% of UDCA-treated patients in studies showed poor adherence.
- AMA-positive patients with currently normal liver tests should still have annual biochemical monitoring.

## Application notes for MedAgent

- This is the basis for the `udca_response_role` fields on ALP, AST, and total bilirubin in `mcp_server/data/reference_ranges.json` (Paris-II criteria specifically, as the most commonly cited 12-month standard).
- The app should never state whether a patient "needs second-line therapy" — it may explain what the Paris-II thresholds are and whether her current values are within them, always framed as information to discuss with her physician, not a recommendation.
