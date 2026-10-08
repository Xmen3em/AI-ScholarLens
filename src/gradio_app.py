"""Gradio client for the typed `/api/v1/stream` SSE contract."""

import html
import json
import os
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx
from src.config import Settings, get_settings
from src.policies.ai_scope import AI_CATEGORY_ALLOWLIST

DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1"


@dataclass
class StreamState:
    answer: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def build_payload(query: str, top_k: int, use_hybrid: bool, model: str, categories: list[str]) -> dict[str, Any]:
    return {
        "query": query,
        "top_k": int(top_k),
        "use_hybrid": use_hybrid,
        "model": model,
        "categories": categories,
    }


def parse_sse_text(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse complete SSE text; production streaming uses the same frame rules."""
    events = []
    for frame in re.split(r"\r?\n\r?\n", text.strip()):
        if not frame:
            continue
        parsed = _parse_frame(frame.splitlines())
        if parsed is not None:
            events.append(parsed)
    return events


def apply_event(state: StreamState, name: str, payload: dict[str, Any]) -> None:
    if name == "sources":
        state.metadata = payload
    elif name == "delta":
        state.answer += str(payload.get("delta", ""))
    elif name == "done":
        state.answer = str(payload.get("answer", state.answer))
    elif name == "error":
        state.answer = ""
        state.error = str(payload.get("error", "Answer generation failed."))
    else:
        raise ValueError("Unexpected SSE event")


def render_output(state: StreamState) -> str:
    if state.error:
        return f"### Error\n\n{html.escape(state.error)}"

    answer = html.escape(state.answer) if state.answer else "_Retrieving evidence…_"
    sections = [f"### Answer\n\n{answer}"]
    citations = state.metadata.get("citations", [])
    if not isinstance(citations, list) or not citations:
        return "\n\n".join(sections)

    links: list[str] = []
    seen = set()
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        arxiv_id = str(citation.get("arxiv_id", ""))
        if arxiv_id in seen or not re.fullmatch(r"[A-Za-z0-9._/-]+", arxiv_id):
            continue
        seen.add(arxiv_id)
        versionless = re.sub(r"v\d+$", "", arxiv_id)
        url = f"https://arxiv.org/pdf/{quote(versionless, safe='/.')}.pdf"
        title = _markdown_text(str(citation.get("title", arxiv_id)))
        links.append(f"{len(links) + 1}. [{title}]({url})")
    if links:
        sections.append("### Papers\n\n" + "\n".join(links))

    evidence = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        marker = _markdown_text(str(citation.get("marker", "")))
        title = _markdown_text(str(citation.get("title", "")))
        section = _markdown_text(str(citation.get("section_title", "")))
        section_index = citation.get("section_index", "?")
        chunk_index = citation.get("chunk_index", "?")
        passage = html.escape(str(citation.get("evidence", "")))
        evidence.append(
            f"**{marker} — {title}, {section}**  \n"
            f"`section_index={section_index}, chunk_index={chunk_index}`\n\n"
            f"<blockquote>{passage}</blockquote>"
        )
    if evidence:
        sections.append("### Evidence\n\n" + "\n\n".join(evidence))
    return "\n\n".join(sections)


async def stream_answer(
    query: str,
    top_k: int,
    use_hybrid: bool,
    model: str,
    categories: list[str],
    *,
    api_base_url: str | None = None,
) -> AsyncIterator[str]:
    state = StreamState()
    yield render_output(state)
    url = f"{api_base_url or os.getenv('RAG_API_BASE_URL', DEFAULT_API_BASE_URL)}/stream"
    payload = build_payload(query, top_k, use_hybrid, model, categories)
    try:
        timeout = httpx.Timeout(300.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            key = os.getenv("API_KEY", "")
            async with client.stream("POST", url, json=payload, headers={"X-API-Key": key} if key else {}) as response:
                if response.is_error:
                    raw = await response.aread()
                    state.error = _api_error(response.status_code, raw)
                    yield render_output(state)
                    return
                async for name, data in _iter_sse(response):
                    apply_event(state, name, data)
                    yield render_output(state)
                    if name in {"done", "error"}:
                        return
        state.answer = ""
        state.error = "The answer stream ended before completion."
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        state.answer = ""
        state.error = "The RAG API is unavailable or returned an invalid stream."
    yield render_output(state)


def build_demo(settings: Settings | None = None):
    import gradio as gr

    settings = settings or get_settings()
    with gr.Blocks(title="AI-ScholarLens Grounded RAG", analytics_enabled=False) as demo:
        gr.Markdown("# AI-ScholarLens\nAsk the indexed arXiv corpus and inspect the exact passages behind the answer.")
        question = gr.Textbox(
            label="Research question",
            placeholder="What evidence do these papers provide?",
            lines=3,
            max_length=500,
        )
        with gr.Row():
            top_k = gr.Slider(1, 10, value=3, step=1, label="Papers")
            use_hybrid = gr.Checkbox(value=True, label="Hybrid retrieval")
            model = gr.Dropdown(
                choices=settings.ollama_models,
                value=settings.ollama_default_model,
                allow_custom_value=False,
                label="Model",
            )
        categories = gr.CheckboxGroup(choices=sorted(AI_CATEGORY_ALLOWLIST), label="arXiv categories (optional)")
        submit = gr.Button("Ask", variant="primary")
        output = gr.Markdown(label="Grounded answer", sanitize_html=True)
        inputs = [question, top_k, use_hybrid, model, categories]
        submit.click(stream_answer, inputs=inputs, outputs=output)
        question.submit(stream_answer, inputs=inputs, outputs=output)
    return demo.queue()


async def _iter_sse(response: httpx.Response) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    frame: list[str] = []
    async for line in response.aiter_lines():
        if line:
            frame.append(line)
            continue
        parsed = _parse_frame(frame)
        frame = []
        if parsed is not None:
            yield parsed
    parsed = _parse_frame(frame)
    if parsed is not None:
        yield parsed


def _parse_frame(lines: list[str]) -> tuple[str, dict[str, Any]] | None:
    event = "message"
    data_lines = []
    for line in lines:
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").lstrip())
    if not data_lines:
        return None
    payload = json.loads("\n".join(data_lines))
    if not isinstance(payload, dict):
        raise ValueError("SSE data must be a JSON object")
    return event, payload


def _api_error(status_code: int, body: bytes) -> str:
    try:
        detail = json.loads(body).get("detail")
    except (json.JSONDecodeError, AttributeError):
        detail = None
    if isinstance(detail, str) and len(detail) <= 300:
        return detail
    return f"The RAG API rejected the request (HTTP {status_code})."


def _markdown_text(value: str) -> str:
    escaped = html.escape(value)
    return re.sub(r"([\\[\]()`*_])", r"\\\1", escaped)
