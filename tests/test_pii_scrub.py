"""Regression tests for guardrails/pii_scrub.py -- both cases come from real
documents that went through the app (values below are made up)."""
from guardrails.pii_scrub import REDACTION_TOKEN, scrub, scrub_narrative_text


def test_dob_without_colon_is_redacted():
    text = "Пациент: Иванова Анна Петровна, дата рождения 03.02.1960\nПечень: правая доля 127 мм"
    out = scrub_narrative_text(text).text
    assert "03.02.1960" not in out
    assert "127 мм" in out


def test_dob_with_colon_still_redacted():
    out = scrub_narrative_text("Дата рождения: 03.02.1960\n").text
    assert "03.02.1960" not in out
    assert REDACTION_TOKEN in out


def test_inline_patient_name_in_capitals_is_redacted():
    out = scrub_narrative_text("Пациентка ИВАНОВА А.П., 1960 г.р. поступила в отделение").text
    assert "ИВАНОВА" not in out
    assert "поступила в отделение" in out


def test_inline_patient_name_title_case_is_redacted():
    out = scrub_narrative_text("Пациентка Иванова Анна Петровна поступила").text
    assert "Иванова" not in out


def test_patient_word_followed_by_lowercase_verb_is_kept():
    text = "Пациентка выписывается с улучшением для дальнейшего наблюдения."
    assert scrub_narrative_text(text).text == text


def test_clinical_datetime_not_mistaken_for_phone():
    text = "Дата поступления в стационар: 04.05.2023 13:08\nДата выписки: 11.05.2023 14:00"
    out = scrub(text).text
    assert "04.05.2023 13:08" in out
    assert "PHONE_NUMBER" not in out


def test_real_phone_number_still_redacted():
    out = scrub("Телефон: +7 701 234 56 78").text
    assert "234 56 78" not in out
