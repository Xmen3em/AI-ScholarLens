"""Optional Deep Agents harness. Install it in the separate research environment.

Verified against deepagents 0.7.28, not imported by the normal Telegram process.
Source: https://docs.langchain.com/oss/python/deepagents/customization
"""

import json
from typing import Any

from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, create_deep_agent, register_harness_profile
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.agents.middleware import wrap_tool_call
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field
from src.services.study.tools import StudyTools

ALLOWED = frozenset({"paper_overview", "search_evidence", "read_evidence"})


class HFStudyChat(BaseChatModel):
    transport: Any = Field(exclude=True, repr=False)
    job_id: str
    model_name: str = "gpt-oss-120b"

    @property
    def _llm_type(self):
        return "scholarlens"

    def _get_ls_params(self, stop=None, **kwargs):
        return {"ls_provider": "scholarlens", "ls_model_name": self.model_name, "ls_model_type": "chat"}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError("Use the asynchronous bounded study interface")

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        wire = [convert_to_openai_tool(t) for t in tools]
        if not wire or any(t["function"]["name"] not in ALLOWED for t in wire):
            raise ValueError("research_tool_allowlist_violation")
        return self.bind(tools=wire)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if stop:
            raise ValueError("study_stop_override_not_supported")
        wire = []
        for message in messages:
            if not isinstance(message.content, str):
                raise ValueError("study_requires_text_messages")
            if isinstance(message, SystemMessage):
                row = {"role": "system", "content": message.content}
            elif isinstance(message, HumanMessage):
                row = {"role": "user", "content": message.content}
            elif isinstance(message, ToolMessage):
                row = {"role": "tool", "content": message.content, "tool_call_id": message.tool_call_id}
            elif isinstance(message, AIMessage):
                row = {"role": "assistant", "content": message.content}
                if message.tool_calls:
                    row["tool_calls"] = [{"id": c["id"], "type": "function", "function": {
                        "name": c["name"], "arguments": json.dumps(c["args"], ensure_ascii=False)}} for c in message.tool_calls]
                for key in ("reasoning_content", "reasoning"):
                    if key in message.additional_kwargs:
                        row[key] = message.additional_kwargs[key]
            else:
                raise ValueError("unsupported_study_role")
            wire.append(row)
        result = await self.transport.complete(self.job_id, "deep_research", wire, tools=kwargs.get("tools"))
        raw = result["message"]
        calls = []
        for call in raw.get("tool_calls") or []:
            function = call["function"]
            if function["name"] not in ALLOWED or type(call.get("id")) is not str or len(call["id"]) > 120:
                raise ValueError("research_tool_call_rejected")
            arguments = json.loads(function["arguments"])
            if type(arguments) is not dict:
                raise ValueError("invalid_tool_arguments")
            calls.append({"id": call["id"], "name": function["name"], "args": arguments})
        usage = result["usage"]
        extra = {key: raw[key] for key in ("reasoning_content", "reasoning") if raw.get(key)}
        answer = AIMessage(content=raw.get("content") or "", tool_calls=calls, additional_kwargs=extra,
                           usage_metadata={"input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"],
                                           "total_tokens": usage["prompt_tokens"] + usage["completion_tokens"]})
        return ChatResult(generations=[ChatGeneration(message=answer)])


def create_study_research(model: HFStudyChat, source: StudyTools, system_prompt: str):
    @tool
    def paper_overview() -> dict:
        """Read the selected paper's identity, coverage and evidence-block directory."""
        return source.overview()

    @tool
    def search_evidence(query: str, limit: int = 6) -> list[dict]:
        """Find original evidence within this paper only; use English technical keywords, limit 1-8."""
        return source.search(query, limit)

    @tool
    def read_evidence(ids: list[str]) -> list[dict]:
        """Read 1-8 exact evidence block IDs from the selected paper; unknown IDs fail."""
        return source.read(ids)

    @wrap_tool_call
    async def enforce_tools(request, handler):
        if request.tool_call["name"] not in ALLOWED:
            raise ValueError("research_tool_execution_denied")
        return await handler(request)

    register_harness_profile("scholarlens", HarnessProfile(
        excluded_tools=frozenset({"ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute", "task", "write_todos"}),
        excluded_middleware=frozenset({"SummarizationMiddleware"}),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
    # SDK 0.7.28 requires read_file even with no filesystem use. Its default
    # backend is virtual state, not the host disk. Hide it and deny its execution
    # independently; no filesystem/write/shell tool reaches the HF adapter.
    return create_deep_agent(model=model, tools=[paper_overview, search_evidence, read_evidence],
        system_prompt=system_prompt, subagents=[], middleware=[FilesystemMiddleware(tools=["read_file"]), enforce_tools],
        checkpointer=None, debug=False, name="scholarlens-paper-study")
