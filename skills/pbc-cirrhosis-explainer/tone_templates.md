# Tone Templates

Pick the template matching the `severity`/`escalation_level` computed
deterministically upstream (`classify_severity_node`) -- never re-derive the
severity from the raw numbers inside this skill.

## critical / seek_care_now

Structure: (1) state plainly which value(s) triggered concern, in calm,
non-alarmist language; (2) explain briefly what that marker reflects; (3)
give a clear, direct instruction to contact her doctor promptly -- not
"consider" or "maybe," a clear call to action; (4) do not speculate about
what it might mean beyond what the retrieved clinical context supports.
Never say "you have X condition."

## worsening / see_doctor_soon

Structure: (1) name the marker(s) trending in the wrong direction and by how
much (use the trend data given, e.g. "risen by 12% since your last test");
(2) explain what that trend generally reflects; (3) give 2-4 CONCRETE,
actionable lifestyle suggestions grounded in the retrieved clinical context
-- diet (e.g. sodium restriction if ascites-relevant), sleep, gentle exercise,
mood/stress -- never suggest a medication change; (4) note this is worth
mentioning at her next doctor visit, sooner if it continues.

## improving / routine

Structure: (1) open with genuine, specific encouragement (use the encouragement
opener phrase from the glossary) naming what improved and by how much; (2)
briefly explain why that's a good sign; (3) reinforce whatever she's currently
doing that's likely helping (medication adherence, lifestyle) without inventing
specifics not in the input; (4) keep tone warm, not clinical.

## stable / routine

Structure: (1) state plainly that values are within the expected range for her
condition (note: mild thrombocytopenia, for example, is EXPECTED in cirrhosis
and should be framed calmly, not as a new concern, per
`mcp_server/data/reference_ranges.json`'s cirrhosis_note fields); (2) brief
context on what's being monitored and why; (3) light, general wellness note
(no urgency).

## Mandatory disclaimer (all templates, both languages, verbatim from glossary)

KZ: Бұл диагноз емес. Нәтижелерді дәрігеріңізбен талқылаңыз.
RU: Это не является диагнозом. Пожалуйста, обсудите результаты с вашим лечащим врачом.
