import httpx
import pytest
from src.commands.diagnose_hf_qualification import diagnose
from src.commands.hf_qualification import load_revision

from tests.unit.test_hf_client import envelope, settings


@pytest.mark.parametrize("rejected", [True, False])
@pytest.mark.anyio
async def test_diagnostic_makes_one_call_and_can_never_qualify_or_collect_cases(stub_httpx, tmp_path, rejected):
    def respond(request):
        if rejected:
            return httpx.Response(400, json={"error": {"type": "invalid_request_error", "code": "json_validate_failed",
                                                       "message": "private response", "failed_generation": "private generated text"}})
        return httpx.Response(200, json=envelope('{"relevant_markers":["[1.1]"]}', usage={"prompt_tokens": 100, "completion_tokens": 20}))

    calls = stub_httpx(respond)
    result = await diagnose(settings(api_rate_limit_path=str(tmp_path / "limits")), load_revision(), memory=lambda: 4096)
    assert len(calls) == result["outbound_attempts"] == 1
    assert result["qualification_accepted"] is False and result["kind"] == "diagnostic_only"
    assert [check["id"] for check in result["qualification"]["checks"]] == ["relevance"]
    if rejected:
        assert result["qualification"]["checks"][0]["calls"][0]["provider_error_code"] == "json_validate_failed"
