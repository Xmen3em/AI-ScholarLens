import copy
import json
from pathlib import Path

import httpx
import pytest
from src.commands import hf_paper_acceptance as acceptance
from src.commands.hf_paper_profile import EVIDENCE_PROFILE, EVIDENCE_TASK_SHA256, PACED_PROFILE, PACED_TASK_SHA256
from src.operations import request_context
from src.services import qualified_pc_api as runtime
from src.services.hf.client import HFGenerationError

from tests.unit.test_hf_client import envelope
from tests.unit.test_hf_paper_acceptance import evidence
from tests.unit.test_hf_paper_client import arguments
from tests.unit.test_hf_tokenizer import install_vocabulary
from tests.unit.test_qualified_pc_api import config


@pytest.fixture(params=[(EVIDENCE_PROFILE, EVIDENCE_TASK_SHA256), (PACED_PROFILE, PACED_TASK_SHA256)])
def selected_profile(request):
    return request.param


def test_evidence_acceptance_lock_retains_profile_through_revalidation(tmp_path, monkeypatch, selected_profile):
    profile_name, manifest_sha = selected_profile
    run, source = evidence(tmp_path, monkeypatch)
    metadata_path = run / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["configuration"]["policy"] = profile_name
    metadata["hosted_manifest_sha256"] = manifest_sha
    metadata_path.write_text(json.dumps(metadata))
    report = acceptance.score_run(run, source, {})
    report["hosted_manifest_sha256"] = manifest_sha

    def score(*args, **kwargs):
        assert kwargs["profile_name"] == profile_name
        return copy.deepcopy(report)

    monkeypatch.setattr(acceptance, "score_run", score)
    lock = acceptance.create_acceptance_lock(run, source)
    assert lock["hosted_manifest_sha256"] == manifest_sha
    path = tmp_path / "lock.json"; path.write_text(json.dumps(lock))
    assert acceptance.validate_acceptance(path)["holdout_accepted"]
    lock["hosted_manifest_sha256"] = "92ec9996534e5a958d4ead38fa9224b83ce6c3a318ca3919d886decaeba2558d"
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError):
        acceptance.validate_acceptance(path)


@pytest.mark.anyio
async def test_evidence_runtime_uses_accepted_catalog_and_rejects_larger_schema_before_wire(tmp_path, monkeypatch, stub_httpx, selected_profile):
    profile_name, manifest_sha = selected_profile
    from src.schemas.api.rag import GeneratedAnswer
    from src.services.rag.service import _selection_pattern

    install_vocabulary(tmp_path, monkeypatch)
    proof = {"model": "openai/gpt-oss-120b:cerebras", "hosted_manifest_sha256": manifest_sha,
             "source_files": {"src/frozen": "source"}}
    monkeypatch.setattr(runtime, "validate_acceptance", lambda p: copy.deepcopy(proof))
    settings = config(tmp_path).model_copy(update={"rag_sentence_candidates_per_passage": 3, "rag_max_sentence_candidates": 10})
    calls = stub_httpx(lambda r: httpx.Response(200, json=envelope('{"in_scope":true}',
                                                usage={"prompt_tokens": 100, "completion_tokens": 20})))
    hf = runtime.QualifiedHF(settings, Path("accepted.json"), memory=lambda: 4096)
    token = request_context.set({"request_id": "private-owner-question"})
    try:
        case = runtime.load_cerebras()["cases"][0]
        await hf.generate_result(settings.hf_default_model, case["prompt"], **arguments(case))
        schema = GeneratedAnswer.model_json_schema()
        schema["properties"]["answer"] = {"type": "string", "pattern": _selection_pattern(11)}
        with pytest.raises(HFGenerationError):
            await hf.generate_result(settings.hf_default_model, "Synthetic oversized catalog", response_format=schema)
        assert len(calls) == 1 and request_context.get()["hf_failed"]
    finally:
        request_context.reset(token)
        await hf.aclose()


def test_evidence_runtime_cannot_start_with_old_candidate_settings(tmp_path, monkeypatch, selected_profile):
    profile_name, manifest_sha = selected_profile
    proof = {"model": "openai/gpt-oss-120b:cerebras", "hosted_manifest_sha256": manifest_sha}
    monkeypatch.setattr(runtime, "validate_acceptance", lambda p: proof.copy())
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: pytest.fail("Mismatched catalog allocated provider client"))
    with pytest.raises(ValueError):
        runtime.QualifiedHF(config(tmp_path), Path("accepted.json"))
