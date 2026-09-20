# Liver Panel Markers: Plain-Language Reference

Source: MedlinePlus Liver Function Tests (medlineplus.gov/lab-tests/liver-function-tests/), condensed for MedAgent RAG index. This is the patient-education register the Skill's glossary and explanation node should draw tone from.

## Albumin
A protein made by the liver. The test measures how much circulates in the blood, reflecting the liver's protein-production capacity. Low albumin signals reduced liver function — but in cirrhosis, this is a *trend* signal (falling over months), not usually a single-reading alarm.

## Total protein
The total amount of protein in the blood, including albumin and globulins. Abnormal levels can indicate liver function problems, but are interpreted alongside albumin, not alone.

## ALP (Alkaline Phosphatase)
An enzyme mostly made in the liver, but also bone. High ALP doesn't automatically mean liver disease — but in a patient with known PBC, ALP is the central marker tracked for disease activity and UDCA treatment response.

## ALT and AST (transaminases)
Enzymes mainly made in the liver (ALT more specifically so than AST, which is also in muscle/heart). Elevated levels typically suggest liver cell inflammation or damage.

## GGT (Gamma-Glutamyl Transferase)
Another liver enzyme; elevation often correlates with bile duct problems or liver stress — relevant to the cholestatic pattern seen in PBC.

## Bilirubin
A yellow waste product from red blood cell breakdown that the liver normally clears. High levels can cause jaundice and yellowing of the eyes/skin, and reflect impaired liver processing. In cirrhosis and PBC specifically, bilirubin is one of the most important trend markers — it is a direct input to both MELD-Na and the Paris-II UDCA-response criteria.

## PT/INR (Prothrombin Time / International Normalized Ratio)
Measures how long blood takes to clot. Prothrombin is a clotting protein made by the liver, so a prolonged time / high INR suggests reduced liver synthetic function — a serious signal when it rises.

## Application notes for MedAgent

Use this plain-language register (concrete, non-alarmist, explains *why* a marker matters rather than just naming it) as the model for `generate_explanation_node` output, refined further by the Skill's PBC/cirrhosis-specific framing and bilingual glossary.
