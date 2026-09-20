# Bilingual Glossary (RU / KZ)

Source of truth for marker names is `mcp_server/data/reference_ranges.json` --
this file mirrors it for quick loading inside the explanation prompt without
pulling in the full JSON, and adds recurring phrases not tied to a marker.

## Liver panel / coagulation / PBC markers

| Code | Russian | Kazakh |
|---|---|---|
| ALT | Аланинаминотрансфераза (АЛТ) | Аланинаминотрансфераза (АЛТ) |
| AST | Аспартатаминотрансфераза (АСТ) | Аспартатаминотрансфераза (АСТ) |
| GGT | Гамма-глутамилтрансфераза (ГГТ) | Гамма-глутамилтрансфераза (ГГТ) |
| ALP | Щелочная фосфатаза (ЩФ) | Сілтілі фосфатаза (ЩФ) |
| BILI_TOTAL | Общий билирубин | Жалпы билирубин |
| BILI_DIRECT | Прямой билирубин | Тікелей билирубин |
| ALBUMIN | Альбумин | Альбумин |
| TOTAL_PROTEIN | Общий белок | Жалпы белок |
| INR | Международное нормализованное отношение (МНО) | Халықаралық қалыпқа келтірілген қатынас (МНО) |
| PLATELETS | Тромбоциты | Тромбоциттер |
| CREATININE | Креатинин | Креатинин |
| SODIUM | Натрий | Натрий |
| AFP | Альфа-фетопротеин (АФП) | Альфа-фетопротеин (АФП) |
| AMA_M2 | Антимитохондриальные антитела, M2 (АМА-M2) | Антимитохондриялық антиденелер, M2 (АМА-M2) |
| PT_SEC | Протромбиновое время (ПВ) | Протромбин уақыты (ПВ) |
| PTI | Протромбиновый индекс (ПТИ) | Протромбин индексі (ПТИ) |
| APTT | Активированное частичное тромбопластиновое время (АЧТВ) | Белсендірілген ішінара тромбопластин уақыты (АЧТВ) |
| FIBRINOGEN | Фибриноген | Фибриноген |
| TT_SEC | Тромбиновое время (ТВ) | Тромбин уақыты (ТВ) |
| IGM | Иммуноглобулин M (IgM) | Иммуноглобулин M (IgM) |

## Condition / concept terms

| Concept | Russian | Kazakh |
|---|---|---|
| Primary biliary cholangitis | Первичный билиарный холангит (ПБХ) | Бірінші реттік билиарлы холангит (ПБХ) |
| Cirrhosis | Цирроз печени | Бауыр циррозы |
| UDCA (ursodeoxycholic acid) | Урсодезоксихолевая кислота (УДХК) | Урсодезоксихолева қышқылы (УДХК) |
| Biochemical response | Биохимический ответ на лечение | Емге биохимиялық жауап |
| MELD-Na score | Индекс MELD-Na | MELD-Na көрсеткіші |
| Fibrosis stage | Стадия фиброза | Фиброз сатысы |
| Portal hypertension | Портальная гипертензия | Портальды гипертензия |

## Recurring phrases

| Purpose | Russian | Kazakh |
|---|---|---|
| Disclaimer (must appear verbatim, checked by `disclaimer_check_node`) | Это не является диагнозом. Пожалуйста, обсудите результаты с вашим лечащим врачом. | Бұл диагноз емес. Нәтижелерді дәрігеріңізбен талқылаңыз. |
| Escalation prompt | Пожалуйста, свяжитесь с вашим врачом в ближайшее время. | Дәрігеріңізге жақын арада хабарласыңыз. |
| Encouragement opener | Хорошая новость — | Қуантарлық жаңалық — |
