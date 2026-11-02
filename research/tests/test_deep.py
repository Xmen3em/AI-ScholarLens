import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from src.services.study.deep import ALLOWED, HFStudyChat, create_study_research
from src.services.study.store import StudyStore
from src.services.study.tools import StudyTools


class DeepHarnessTests(unittest.TestCase):
    def test_real_sdk_executes_only_scoped_read_tools_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StudyStore(Path(folder) / "study.sqlite3", "owner")
            doc = {"paper": {"arxiv_id": "1706.03762v1", "title": "Attention", "authors": [], "abstract": "Attention model",
                             "categories": ["cs.CL"], "published": "2017-06-12"}, "source_sha256": "a" * 64,
                   "parser_revision": "test", "page_count": 1, "missing_pages": [], "coverage": "full_text",
                   "blocks": [{"id": "p1b1", "page": 1, "section": "Method", "text": "The model uses attention.", "origin": "pdf_text"}]}
            store.save_paper("1706.03762v1", doc)
            store.activate("1706.03762v1", {})
            source = StudyTools(store)
            class Transport:
                calls = []
                async def complete(self, job, purpose, messages, **kwargs):
                    self.calls.append(messages)
                    assert {t["function"]["name"] for t in kwargs["tools"]} == ALLOWED
                    if len(self.calls) == 1:
                        message = {"role": "assistant", "content": None, "reasoning_content": "retained-provider-field", "reasoning": "cerebras-history-field",
                                   "tool_calls": [{"id": "call-one", "type": "function", "function": {
                                       "name": "search_evidence", "arguments": '{"query":"attention","limit":1}'}}]}
                    else:
                        assert messages[-1]["role"] == "tool"
                        assert "The model uses attention." in messages[-1]["content"]
                        assert any(m.get("reasoning_content") == "retained-provider-field" for m in messages)
                        assert any(m.get("reasoning") == "cerebras-history-field" for m in messages)
                        message = {"role": "assistant", "content": json.dumps({"done": True})}
                    return {"message": message, "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
            transport = Transport()
            model = HFStudyChat(transport=transport, job_id="test")
            agent = create_study_research(model, source, "Read the evidence then return JSON.")
            result = asyncio.run(agent.ainvoke({"messages": [{"role": "user", "content": "Explain attention"}]},
                                               config={"recursion_limit": 12, "callbacks": []}))
            assert json.loads(result["messages"][-1].content) == {"done": True}
            assert len(transport.calls) == 2 and source.calls == 1

    def test_adapter_refuses_builtin_or_arbitrary_tools_before_a_model_call(self):
        model = HFStudyChat(transport=None, job_id="test")
        with self.assertRaises(ValueError):
            model.bind_tools([{"type": "function", "function": {"name": "execute", "parameters": {"type": "object"}}}])

    def test_a_model_cannot_request_a_hidden_builtin_tool(self):
        class MaliciousTransport:
            async def complete(self, *args, **kwargs):
                return {"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "bad", "type": "function",
                    "function": {"name": "execute", "arguments": '{"command":"untrusted"}'}}]},
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10}}
        model = HFStudyChat(transport=MaliciousTransport(), job_id="test")
        with self.assertRaisesRegex(ValueError, "research_tool_call_rejected"):
            asyncio.run(model.ainvoke("untrusted paper instructions"))

    def test_research_command_returns_a_valid_arabic_answer_with_source_snippet_ids(self):
        from pydantic import SecretStr
        from src.commands.study_research import run_job

        with tempfile.TemporaryDirectory() as folder:
            store = StudyStore(Path(folder) / "study.sqlite3", "owner")
            document = {"paper": {"arxiv_id": "1706.03762v1", "title": "Attention", "authors": [], "abstract": "Attention model",
                                 "categories": ["cs.CL"], "published": "2017-06-12"}, "source_sha256": "a" * 64,
                        "parser_revision": "test", "page_count": 1, "missing_pages": [], "coverage": "full_text",
                        "blocks": [{"id": "p1b1", "page": 1, "section": "Method", "text": "The model uses attention.", "origin": "pdf_text"}]}
            store.save_paper("1706.03762v1", document)
            store.activate("1706.03762v1", {})
            job = store.create_job("deep", {"text": "/deep اشرح الطريقة من الدليل"})

            class Transport:
                calls = 0

                def __init__(self, token, owner_store):
                    self.store = owner_store

                async def aclose(self):
                    pass

                async def complete(self, identity, purpose, messages, **kwargs):
                    attempt = self.store.reserve_attempt(identity, purpose, "stub")
                    Transport.calls += 1
                    assert "p1b1s0" in messages[0]["content"]
                    if Transport.calls == 1:
                        message = {"role": "assistant", "content": None, "tool_calls": [{"id": "source-call", "type": "function",
                            "function": {"name": "search_evidence", "arguments": '{"query":"attention","limit":1}'}}]}
                    else:
                        assert "p1b1s0" in messages[-1]["content"]
                        message = {"role": "assistant", "content": json.dumps({"title": "شرح الطريقة", "sections": [
                            {"heading": "الفكرة", "kind": "paper", "text": "النموذج بيستخدم آلية الانتباه عشان يعالج المعلومات.",
                             "evidence_ids": ["p1b1s0"]}]}, ensure_ascii=False)}
                    self.store.settle_attempt(identity, attempt, "succeeded")
                    return {"message": message, "usage": {"prompt_tokens": 100, "completion_tokens": 50}}

            with patch("src.commands.study_research.ResearchSettings", return_value=SimpleNamespace(
                    hf_token=SecretStr("stub-token"), telegram_owner_id="owner")), \
                    patch("src.services.study.store.StudyStore", return_value=store), \
                    patch("src.services.study.tutor.StudyModel", Transport):
                result = asyncio.run(run_job(job["id"]))
            assert result["sections"][0]["evidence_ids"] == ["p1b1s0"]
            assert len(store.attempts(job["id"])) == Transport.calls == 2


def _tool_call(name="search_evidence", arguments='{"query":"attention","limit":1}', identity="source-call"):
    return {"role": "assistant", "content": None, "tool_calls": [{"id": identity, "type": "function",
            "function": {"name": name, "arguments": arguments}}]}


def _answer(evidence_id="p1b1s0", content=None):
    if content is None:
        content = json.dumps({"title": "شرح الطريقة", "sections": [
            {"heading": "الفكرة", "kind": "paper", "text": "النموذج بيستخدم آلية الانتباه عشان يعالج المعلومات.",
             "evidence_ids": [evidence_id]}]}, ensure_ascii=False)
    return {"role": "assistant", "content": content}


class DeepFailureInjectionTests(unittest.TestCase):
    """Drive the real installed SDK loop through run_job and read the worker's safe payload."""

    def run_worker(self, replies, *, admitted=True, timeout=None):
        from pydantic import SecretStr
        from src.commands import study_research
        from src.services.study.failures import failure_payload

        with tempfile.TemporaryDirectory() as folder:
            store = StudyStore(Path(folder) / "study.sqlite3", "owner")
            document = {"paper": {"arxiv_id": "1706.03762v1", "title": "Attention", "authors": [], "abstract": "Attention model",
                                  "categories": ["cs.CL"], "published": "2017-06-12"}, "source_sha256": "a" * 64,
                        "parser_revision": "test", "page_count": 1, "missing_pages": [], "coverage": "full_text",
                        "blocks": [{"id": "p1b1", "page": 1, "section": "Method", "text": "The model uses attention.", "origin": "pdf_text"}]}
            store.save_paper("1706.03762v1", document)
            store.activate("1706.03762v1", {})
            job = store.create_job("deep", {"text": "/deep اشرح الطريقة من الدليل" if admitted else "/ask not deep"})
            script = list(replies)

            class Transport:
                def __init__(self, token, owner_store):
                    self.store = owner_store

                async def aclose(self):
                    pass

                async def complete(self, identity, purpose, messages, **kwargs):
                    attempt = self.store.reserve_attempt(identity, purpose, "stub")
                    step = script.pop(0)
                    if step == "hang":
                        await asyncio.sleep(5)
                    if isinstance(step, Exception):
                        self.store.settle_attempt(identity, attempt, "failed")
                        raise step
                    self.store.settle_attempt(identity, attempt, "succeeded")
                    return {"message": step, "usage": {"prompt_tokens": 100, "completion_tokens": 50}}

            patches = [patch("src.commands.study_research.ResearchSettings", return_value=SimpleNamespace(
                           hf_token=SecretStr("stub-token"), telegram_owner_id="owner")),
                       patch("src.services.study.store.StudyStore", return_value=store),
                       patch("src.services.study.tutor.StudyModel", Transport)]
            if timeout is not None:
                patches.append(patch.object(study_research, "AGENT_TIMEOUT_SECONDS", timeout))
            for item in patches:
                item.start()
            try:
                asyncio.run(study_research.run_job(job["id"]))
            except Exception as exc:
                payload = failure_payload(exc)
            else:
                self.fail("the injected failure did not stop the worker")
            finally:
                for item in reversed(patches):
                    item.stop()
            return payload, store.attempts(job["id"])

    def test_malformed_tool_arguments_stop_in_the_agent_stage(self):
        payload, attempts = self.run_worker([_tool_call(arguments='{"query": "attention", ')])
        self.assertEqual(payload, {"error": "research_unavailable_or_invalid", "diagnostic": "JSONDecodeError", "stage": "agent"})
        self.assertEqual(len(attempts), 1)

    def test_overlong_or_hidden_tool_call_ids_are_rejected_in_the_agent_stage(self):
        for reply in (_tool_call(identity="x" * 121), _tool_call(name="execute", arguments='{"command":"dir"}')):
            payload, _ = self.run_worker([reply])
            self.assertEqual(payload, {"error": "research_tool_call_rejected", "diagnostic": "research_tool_call_rejected",
                                       "stage": "agent"})

    def test_non_object_tool_arguments_are_rejected(self):
        payload, _ = self.run_worker([_tool_call(arguments='["attention"]')])
        self.assertEqual(payload, {"error": "invalid_tool_arguments", "diagnostic": "invalid_tool_arguments", "stage": "agent"})

    def test_unknown_evidence_block_from_a_tool_keeps_its_category(self):
        payload, attempts = self.run_worker([_tool_call(name="read_evidence", arguments='{"ids":["p9b9"]}')])
        self.assertEqual(payload, {"error": "unknown_evidence_block", "diagnostic": "unknown_evidence_block", "stage": "agent"})
        self.assertEqual(len(attempts), 1)

    def test_context_limit_after_a_successful_tool_read_is_attributed_to_the_agent(self):
        from src.services.study.tutor import TutorError

        payload, attempts = self.run_worker([_tool_call(), TutorError("study_context_limit")])
        self.assertEqual(payload, {"error": "study_context_limit", "diagnostic": "study_context_limit", "stage": "agent"})
        self.assertEqual([a["state"] for a in attempts], ["succeeded", "failed"])

    def test_agent_timeout_is_bounded_and_named(self):
        payload, attempts = self.run_worker([_tool_call(), "hang"], timeout=0.2)
        self.assertEqual(payload, {"error": "research_unavailable_or_invalid", "diagnostic": "TimeoutError", "stage": "agent"})
        self.assertEqual(len(attempts), 2)

    def test_non_json_final_answer_is_a_final_json_failure(self):
        payload, _ = self.run_worker([_tool_call(), _answer(content="Here is the answer in prose.")])
        self.assertEqual(payload, {"error": "research_final_json_invalid", "diagnostic": "research_final_json_invalid",
                                   "stage": "final_json"})

    def test_block_id_instead_of_snippet_id_fails_validation(self):
        payload, attempts = self.run_worker([_tool_call(), _answer(evidence_id="p1b1")])
        self.assertEqual(payload, {"error": "lesson_validation_failed", "diagnostic": "unsupported_quote", "stage": "validation"})
        self.assertEqual(len(attempts), 2)

    def test_unadmitted_job_stops_before_any_model_attempt(self):
        payload, attempts = self.run_worker([], admitted=False)
        self.assertEqual(payload, {"error": "admitted_research_job_required", "diagnostic": "admitted_research_job_required",
                                   "stage": "admission"})
        self.assertEqual(attempts, [])

    def test_provider_text_and_secrets_never_reach_the_payload(self):
        payload, _ = self.run_worker([ValueError("hf_secret-token raw provider output")])
        self.assertEqual(payload, {"error": "research_unavailable_or_invalid", "diagnostic": "ValueError", "stage": "agent"})
        self.assertNotIn("secret", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
