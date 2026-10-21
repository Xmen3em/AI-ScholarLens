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


if __name__ == "__main__":
    unittest.main()
