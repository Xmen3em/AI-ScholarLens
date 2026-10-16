import pytest
from src.services.study.store import StudyStore
from src.services.study.tools import StudyTools

from tests.unit.test_study_service import Content, paper


@pytest.mark.anyio
async def test_tools_are_snapshot_scoped_validate_ids_and_have_one_shared_budget(tmp_path):
    store = StudyStore(tmp_path / "store.sqlite3", "owner")
    doc = await Content().acquire(paper())
    store.save_paper(doc.paper.arxiv_id, doc.model_dump())
    store.activate(doc.paper.arxiv_id, {"title": doc.paper.title})
    tools = StudyTools(store, max_calls=3)
    store.activate("another-paper", {})
    assert tools.overview()["paper"]["arxiv_id"] == doc.paper.arxiv_id
    assert tools.search("attention")[0]["id"] == "p1b1"
    with pytest.raises(ValueError, match="unknown_evidence"):
        tools.read(["p99b99"])
    with pytest.raises(ValueError, match="budget"):
        tools.read(["p1b1"])
    with pytest.raises(ValueError, match="active_paper"):
        StudyTools(StudyStore(store.path, "someone-else"))


def test_total_smoke_budget_is_durable_and_forget_cannot_reset_it(tmp_path):
    store = StudyStore(tmp_path / "store.sqlite3", "smoke")
    store.set_total_ceiling(1)
    job = store.create_job("one", {})
    store.reserve_attempt(job["id"], "test", "model")
    store.finish_job(job["id"], {"text": "done"})
    store.forget()
    new = StudyStore(store.path, "smoke")
    with pytest.raises(RuntimeError):
        new.set_total_ceiling(2)
    second = new.create_job("two", {})
    with pytest.raises(RuntimeError):
        new.reserve_attempt(second["id"], "test", "model")
