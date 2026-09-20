# Clinical corpus sources

Content in this folder is condensed/summarized from the sources below, not reproduced verbatim in bulk, and always cited by title in generated answers per the RAG design (Section 5, plan). Repo is private/mentor-access-only, which permits this kind of working corpus; sources are still listed here for attribution and so the corpus can be re-verified or expanded against the originals.

| File | Topic | Primary source | License/access note |
|---|---|---|---|
| `01_pbc_diagnosis_udca_response.md` | PBC diagnosis criteria, UDCA dosing, Paris-II/Toronto/GLOBE biochemical response criteria | APASL clinical practice guidance summary, PMC (https://pmc.ncbi.nlm.nih.gov/articles/PMC8843914/) | Open access (PMC) |
| `02_kz_protocol_cirrhosis.md` | Kazakhstan MoH clinical protocol for liver cirrhosis — CTP/MELD grading, monitoring markers, imaging, complication management, PBC note | diseases.medelement.com, RK MoH Protocol No. 135 (2020) (https://diseases.medelement.com/disease/цирроз-печени-у-взрослых-кп-рк-2020/16681) | Publicly published KZ MoH protocol, reproduced for internal RAG use |
| `03_cirrhosis_patient_overview.md` | Plain-language cirrhosis overview (what it is, causes, symptoms, management) | MedlinePlus, U.S. NLM (https://medlineplus.gov/cirrhosis.html) | Public domain (U.S. government work) |
| `04_liver_panel_markers_plain_language.md` | Plain-language explanation of each liver marker | MedlinePlus Lab Tests (https://medlineplus.gov/lab-tests/liver-function-tests/) | Public domain (U.S. government work) |
| `05_ascites_hrs_aasld.md` | Ascites/HRS/SBP significance and escalation framing | AASLD Practice Guidance summary (https://www.aasld.org/practice-guidelines/diagnosis-evaluation-and-management-ascites-spontaneous-bacterial-peritonitis) | AASLD public guideline summary page |
| `06_fibroscan_results_explained.md` | FibroScan kPa/CAP interpretation, fibrosis staging | Memorial Sloan Kettering patient education (https://www.mskcc.org/cancer-care/patient-education/understanding-your-fibroscan-results) | Institutional patient-education page |

## Access notes / known gaps (for Day 3 RAG-build follow-up)

- The full AASLD 2018 PBC Practice Guidance PDF (aasld.org/sites/default/files/.../PracticeGuidelines-PBC-November2018_1.pdf) and the EASL Journal of Hepatology PBC guideline returned 402/403 (paywalled/blocked) via direct fetch — worked around using the open-access APASL PMC summary instead (`01_pbc_diagnosis_udca_response.md`), which covers the same diagnostic/UDCA-response content. If deeper AASLD/EASL primary-source detail is wanted later, try the AASLD PDF via a browser session (it may just be bot-blocked, not truly paywalled) rather than WebFetch.
- **Still to add** before the corpus is considered complete (~15-25 doc target from the plan): a dedicated hepatic encephalopathy management page (beyond the West-Haven grading already captured in `02_kz_protocol_cirrhosis.md`), a MELD-Na calculation reference, and 1-2 more general patient-education pages (e.g. diet/sodium guidance for cirrhosis, itch/pruritus management specific to PBC/cholestasis). Flagged for Day 1 continuation or Day 3 alongside the `build_index.py` work.
- No native Kazakh-language clinical source was found at usable scale (consistent with the plan's documented bilingual-corpus trade-off) — the KZ protocol itself is Russian-language.
- **Action item for Day 3**: user will search for and add any PBC-specific (not just general cirrhosis) Kazakhstani protocol PDF, plus any other doctor-provided guideline documents, directly into this folder before `build_index.py` runs. Check `rag/corpus/clinical/` for new files at the start of Day 3 before finalizing the corpus list.
