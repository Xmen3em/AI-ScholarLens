import json

import httpx
import pytest
from src.commands.hf_evaluation import MeasuredHF
from src.services.hf.client import HFGenerationError

from tests.unit.test_hf_client import OPTIONS, PRIVATE_QUESTION, settings
from tests.unit.test_hf_configuration import MODEL, TOKEN


@pytest.mark.parametrize("body,code,kind", [
    ({"error": {"code": "json_validate_failed", "type": "invalid_request_error", "message": TOKEN, "failed_generation": PRIVATE_QUESTION}}, "json_validate_failed", "invalid_request_error"),
    ({"error": {"code": TOKEN, "type": PRIVATE_QUESTION, "message": TOKEN}}, None, None),
    ({"error": {"code": ["json_validate_failed"], "type": {"value": "invalid_request_error"}}}, None, None),
    ({"error": {"type": "invalid_request_error"}}, None, "invalid_request_error"),
])
@pytest.mark.anyio
async def test_only_allowlisted_provider_error_metadata_is_retained(stub_httpx, body, code, kind):
    calls = stub_httpx(lambda request: httpx.Response(400, json=body))
    hf = MeasuredHF(settings(), outbound_budget=1)
    try:
        with pytest.raises(HFGenerationError) as error:
            await hf.generate(MODEL, "synthetic", options=OPTIONS)
        assert error.value.error_code == code and error.value.error_type == kind
        assert error.value.status_code == 400 and len(calls) == 1
        ledger = hf.ledger["administrative"][0]
        assert ledger.get("provider_error_code") == code and ledger.get("provider_error_type") == kind
        serialized = json.dumps(ledger) + str(error.value)
        assert TOKEN not in serialized and PRIVATE_QUESTION not in serialized
        assert "failed_generation" not in serialized
    finally:
        await hf.aclose()


@pytest.mark.parametrize("body", [b"x" * 9000, b"not JSON", b'{"error":{"code":"json_validate_failed","code":"context_length_exceeded"}}'],
                         ids=["oversize", "malformed", "duplicate"])
@pytest.mark.anyio
async def test_oversized_malformed_or_duplicate_error_bodies_never_supply_diagnostics(stub_httpx, body):
    calls = stub_httpx(lambda request: httpx.Response(400, content=body))
    hf = MeasuredHF(settings(), outbound_budget=1)
    try:
        with pytest.raises(HFGenerationError) as error:
            await hf.generate(MODEL, "synthetic", options=OPTIONS)
        assert error.value.error_code is None and error.value.error_type is None
        assert len(calls) == hf.attempts == 1
    finally:
        await hf.aclose()
