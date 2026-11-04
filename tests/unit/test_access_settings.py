import pytest
from pydantic import ValidationError
from src.services.study import access_text
from src.services.study.access_settings import AccessSettings


def test_defaults_match_the_spec():
    s = AccessSettings(_env_file=None)
    assert (s.multi_user, s.daily_papers, s.daily_questions, s.daily_usd_ceiling, s.parallel_jobs,
            s.messages_per_minute, s.retention_days) == (False, 3, 30, 2.00, 3, 6, 30)


@pytest.mark.parametrize("name,value", [("PARALLEL_JOBS", "5"), ("PARALLEL_JOBS", "0"), ("DAILY_USD_CEILING", "0"),
                                        ("RETENTION_DAYS", "0"), ("DAILY_PAPERS", "-1"), ("MESSAGES_PER_MINUTE", "61")])
def test_out_of_range_settings_refuse(monkeypatch, name, value):
    monkeypatch.setenv("STUDY_" + name, value)
    with pytest.raises(ValidationError):
        AccessSettings(_env_file=None)


def test_settings_read_the_study_prefix(monkeypatch):
    monkeypatch.setenv("STUDY_MULTI_USER", "true")
    monkeypatch.setenv("STUDY_DAILY_PAPERS", "5")
    s = AccessSettings(_env_file=None)
    assert s.multi_user is True and s.daily_papers == 5


def test_message_templates_format():
    assert access_text.USAGE.format(p=2, P=3, q=24, Q=30).startswith("النهارده: فاضلك 2 من 3 ورقة و24 من 30 سؤال.")
    assert "إنت رقم 2" in access_text.QUEUED.format(n=2)
    assert access_text.PAPERS_USED.format(P=3).startswith("خلّصت ورق النهارده (3 من 3)")
    assert access_text.QUESTIONS_USED.format(Q=30).startswith("خلّصت أسئلة النهارده (30 من 30)")


def test_privacy_note_states_retention_and_forget():
    assert "30 يوم" in access_text.PRIVACY and "/forget" in access_text.PRIVACY and "GLM-5.3" in access_text.PRIVACY


def test_help_lines_name_the_commands():
    assert all(command in " ".join(access_text.STUDENT_HELP_LINES) for command in ("/usage", "/privacy", "/forget"))
    assert all(command in " ".join(access_text.OWNER_HELP_LINES) for command in ("/invite", "/members", "/revoke", "/usage"))
