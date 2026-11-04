import pytest
from src.services.study.store import StoreConflict, StudyStore


def test_intent_admission_is_durable_and_a_changed_payload_cannot_reuse_it(tmp_path):
    path = tmp_path / "study.sqlite3"
    store = StudyStore(path, "owner-a", now=lambda: 1000)
    first = store.create_job("tg:1", {"text": "1706.03762"})
    assert StudyStore(path, "owner-a", now=lambda: 1000).create_job("tg:1", {"text": "1706.03762"}) == first
    with pytest.raises(StoreConflict):
        store.create_job("tg:1", {"text": "a different paper"})
    assert StudyStore(path, "owner-b", now=lambda: 1000).get_job(first["id"]) is None


def test_only_one_active_intent_can_start_and_completed_results_can_be_retrieved(tmp_path):
    store = StudyStore(tmp_path / "study.sqlite3", "owner-a")
    first = store.create_job("tg:1", {"text": "paper"})
    with pytest.raises(StoreConflict):
        store.create_job("tg:2", {"text": "other paper"})
    store.finish_job(first["id"], {"text": "a result"})
    assert store.get_job(first["id"])["result"] == {"text": "a result"}
    assert store.create_job("tg:2", {"text": "other paper"})["id"] != first["id"]


def test_unknown_model_attempt_prevents_automatic_replay_after_recovery(tmp_path):
    path = tmp_path / "study.sqlite3"
    store = StudyStore(path, "owner-a")
    job = store.create_job("tg:1", {"text": "paper"}, max_calls=2)
    attempt = store.reserve_attempt(job["id"], "lesson", "test-model")
    assert attempt == 1
    recovered = StudyStore(path, "owner-a")
    recovered.recover_interrupted()
    assert recovered.get_job(job["id"])["status"] == "interrupted"
    with pytest.raises(StoreConflict):
        recovered.reserve_attempt(job["id"], "lesson", "test-model")
    assert recovered.attempts(job["id"])[0]["state"] == "unknown"
    assert recovered.create_job("tg:1", {"text": "paper"})["status"] == "interrupted"


def test_failed_attempts_count_against_the_same_intent_budget(tmp_path):
    store = StudyStore(tmp_path / "study.sqlite3", "owner-a")
    job = store.create_job("tg:1", {"text": "paper"}, max_calls=2)
    for expected in (1, 2):
        sequence = store.reserve_attempt(job["id"], "lesson", "test-model")
        assert sequence == expected
        store.settle_attempt(job["id"], sequence, "failed")
    with pytest.raises(StoreConflict):
        store.reserve_attempt(job["id"], "lesson", "test-model")
    assert len(store.attempts(job["id"])) == 2


def test_recent_context_is_paper_scoped_bounded_and_expires(tmp_path):
    clock = [1000]
    path = tmp_path / "study.sqlite3"
    store = StudyStore(path, "owner-a", now=lambda: clock[0])
    store.activate("paper-a", {"title": "Paper A"})
    for index in range(8):
        store.append_turn("paper-a", f"question {index}", f"answer {index}")
    assert len(store.context()["turns"]) == 4
    store.activate("paper-b", {"title": "Paper B"})
    assert store.context()["turns"] == []
    assert store.context()["paper_id"] == "paper-b"
    assert StudyStore(path, "owner-b").context() is None
    clock[0] += 86401
    assert store.context()["turns"] == []


def test_explicit_preferences_survive_sessions_and_forget_removes_study_associations(tmp_path):
    store = StudyStore(tmp_path / "study.sqlite3", "owner-a")
    store.set_preferences(depth="researcher")
    store.activate("paper-a", {"title": "Paper A"})
    store.append_turn("paper-a", "question", "answer")
    store.forget()
    assert store.context() is None
    assert store.preferences() == {"depth": "beginner"}


def test_a_delivery_is_reserved_before_sending_and_cannot_be_claimed_twice(tmp_path):
    path = tmp_path / "study.sqlite3"
    store = StudyStore(path, "owner-a")
    job = store.create_job("tg:1", {"text": "paper"})
    store.finish_job(job["id"], {"text": "lesson"})
    assert store.claim_delivery(job["id"]) is True
    assert StudyStore(path, "owner-a").claim_delivery(job["id"]) is False


def test_retention_and_forget_preserve_admission_without_retaining_the_question(tmp_path):
    clock = [1000]
    store = StudyStore(tmp_path / "study.sqlite3", "owner", now=lambda: clock[0])
    job = store.create_job("one", {"text": "private learner question"})
    store.finish_job(job["id"], {"text": "private learner answer"})
    store.forget()
    redacted = store.create_job("one", {"text": "private learner question"})
    assert redacted["payload"] == {} and redacted["result"] is None
    clock[0] += 31 * 86400
    second = store.create_job("two", {"text": "another question"})
    store.finish_job(second["id"], {"text": "another answer"})
    clock[0] += 31 * 86400
    store.create_job("three", {})
    assert store.get_job(second["id"])["payload"] == {} and store.get_job(second["id"])["result"] is None


def test_recovery_covers_every_owner(tmp_path):
    import json

    from src.services.study.store import recover_all_interrupted

    path = tmp_path / "s.sqlite3"
    stores = [StudyStore(path, owner) for owner in ("1", "2")]
    jobs = [store.create_job(f"t{index}", {}, max_calls=2) for index, store in enumerate(stores)]
    stores[0].reserve_attempt(jobs[0]["id"], "lesson", "m")
    assert recover_all_interrupted(path) == 2
    for store, job in zip(stores, jobs):
        assert store.get_job(job["id"])["status"] == "interrupted"
    assert stores[0].attempts(jobs[0]["id"])[0]["state"] == "unknown"
    assert "مش هيتعاد" in json.dumps(stores[1].get_job(jobs[1]["id"])["result"], ensure_ascii=False)


def test_pending_deliveries_span_owners_oldest_first(tmp_path):
    from src.services.study.store import pending_deliveries_all

    path = tmp_path / "s.sqlite3"
    clock = iter(range(100, 200))
    stores = {owner: StudyStore(path, owner, now=lambda: next(clock)) for owner in ("1", "2")}
    ids = []
    for owner in ("2", "1", "2", "1", "2", "1"):
        job = stores[owner].create_job(f"t{len(ids)}", {}, max_calls=1)
        stores[owner].finish_job(job["id"], {"text": "x"})
        ids.append((owner, job["id"]))
    pending = pending_deliveries_all(path)
    assert [(row["owner"], row["id"]) for row in pending] == ids[:5]
    stores["2"].claim_delivery(ids[0][1])
    assert pending_deliveries_all(path)[0]["id"] == ids[1][1]


def test_store_uses_wal(tmp_path):
    import sqlite3

    StudyStore(tmp_path / "s.sqlite3", "1")
    assert sqlite3.connect(tmp_path / "s.sqlite3").execute("PRAGMA journal_mode").fetchone()[0] == "wal"
