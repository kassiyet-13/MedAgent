# Portal Hypertension and Esophageal Varices — Key Points for Patient Explanation

Source: Cleveland Clinic patient education (my.clevelandclinic.org/health/diseases/15429-esophageal-varices) and AASLD 2023 Practice Guidance on risk stratification and management of portal hypertension and varices in cirrhosis, condensed for MedAgent RAG index. Parallel in structure to `05_ascites_hrs_aasld.md`'s treatment of ascites/HRS — this file covers the other major cirrhosis complication not yet in the corpus.

## What's happening physiologically

Cirrhosis scars the liver, which makes it harder for blood to flow through it. This backs up pressure in the portal vein system (portal hypertension — already introduced briefly in `02_kz_protocol_cirrhosis.md` and `03_cirrhosis_patient_overview.md`), which pushes blood into smaller, thinner-walled backup veins — most importantly, veins in the lower esophagus and upper stomach. Under sustained high pressure, these veins enlarge into varices, which are fragile and can rupture.

## How common and how serious

Roughly half of patients with cirrhosis have esophageal varices at diagnosis, and up to about half of those with varices will experience a bleeding episode at some point. Bleeding risk rises with variceal size (larger varices, generally cited as over 5mm, are meaningfully higher risk) and with more advanced liver disease. A bleeding episode is a medical emergency, not a symptom to manage at home.

## Screening

Patients diagnosed with cirrhosis are generally recommended to have an upper endoscopy (ЭГДС, already mentioned in `02_kz_protocol_cirrhosis.md`) to check for varices, since they typically cause no symptoms until they bleed. Follow-up interval depends on findings and whether the patient is on preventive medication:

- No varices, ongoing liver injury: endoscopy roughly annually.
- No varices, stable/quiescent disease: roughly every 2 years.
- Already on a nonselective beta-blocker for prevention (see below) and no prior bleeding history: routine repeat endoscopy is generally not needed, since the medication itself is doing the preventive work regardless of variceal size changes.

## Prevention (primary prophylaxis)

Two evidence-based approaches, often chosen based on variceal size/risk and patient factors:

- **Nonselective beta-blockers** (e.g., carvedilol, cited in the 2023 AASLD update as a preferred option) — reduce portal pressure and have been shown to lower the risk of a first bleed, and more recent evidence also supports their use for reducing overall decompensation risk in patients with clinically significant portal hypertension, not just bleeding risk specifically. General figures cited for beta-blockers in patient materials: bleeding risk reduction on the order of 50%.
- **Endoscopic band ligation** — placing elastic bands around varices during endoscopy to cut off their blood supply, typically used for higher-risk varices or when beta-blockers aren't suitable/tolerated.

## Recognizing a bleed — when to seek emergency care

Signs of variceal bleeding are a medical emergency and should prompt immediate care, not a wait-and-see approach:

- Vomiting blood (bright red or "coffee-ground" appearance)
- Black, tarry, foul-smelling stool, or visibly bloody stool
- Lightheadedness, fainting, rapid heartbeat, pale or clammy skin (signs of significant blood loss)

## Emergency treatment (for context, not action)

Hospital management of active variceal bleeding typically includes IV fluids/blood transfusion, medication to reduce portal pressure (e.g., octreotide), and urgent endoscopy with band ligation; TIPS (a shunt procedure) or surgical options are used when endoscopic treatment isn't sufficient. This is included here for context only — never something the app should walk a patient through as self-management; the correct action for any suspected bleed is emergency care.

## Application notes for MedAgent

- Mirrors `05_ascites_hrs_aasld.md`'s escalation framing: variceal bleeding symptoms (vomiting blood, black stools, fainting) should be treated by `escalate_node` as an urgent/emergency flag, calm but unambiguous about needing immediate medical attention — never something to "monitor and see."
- The app should not comment on whether a specific patient's varices (e.g., from an endoscopy report) are at "high" or "low" risk of bleeding, or recommend for/against beta-blockers vs. banding — that grading and treatment choice belongs to the endoscopist/hepatologist.
