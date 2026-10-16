import httpx
import pytest
from pydantic import SecretStr
from src.services.study.ocr import RemoteOCR
from src.services.study.store import StudyStore
from src.services.study.tutor import TutorError


@pytest.mark.anyio
async def test_ocr_is_one_bounded_vision_attempt_and_returns_untrusted_text(tmp_path):
    store = StudyStore(tmp_path / "store.sqlite3", "owner")
    job = store.create_job("ocr", {})
    seen = []
    def respond(request):
        import json
        payload = json.loads(request.content)
        seen.append(payload)
        assert store.attempts(job["id"])[0]["model"] == "lightonai/LightOnOCR-2-1B:featherless-ai"
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "The model uses attention."}}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        ocr = RemoteOCR(SecretStr("private-test"), store, client=client, memory=lambda: 2000)
        assert await ocr.extract_page(job["id"], b"\x89PNG\r\n\x1a\n" + b"x" * 20) == "The model uses attention."
    assert len(seen) == 1 and seen[0]["max_tokens"] == 2500
    assert store.attempts(job["id"])[0]["state"] == "succeeded"


@pytest.mark.anyio
async def test_ocr_failure_does_not_retry_or_substitute_a_provider(tmp_path):
    store = StudyStore(tmp_path / "store.sqlite3", "owner")
    job = store.create_job("ocr", {}, max_calls=1)
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(402)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        ocr = RemoteOCR(SecretStr("private-test"), store, client=client, memory=lambda: 2000)
        with pytest.raises(TutorError):
            await ocr.extract_page(job["id"], b"\x89PNG\r\n\x1a\n" + b"x" * 20)
    assert len(seen) == 1 and len(store.attempts(job["id"])) == 1
