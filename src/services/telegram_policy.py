"""Private-owner Telegram input and bounded plain-text replies."""

import re
from dataclasses import dataclass

from pydantic import ValidationError
from src.schemas.api.agent import AgentResponse
from src.schemas.api.rag import AskRequest
from src.services.rag.context import validate_answer_evidence

HELP_TEXT = "Ask about AI/ML research papers. Send a question or /ask followed by your question (up to 500 characters). Answers include source citations."


@dataclass(frozen=True)
class BotAction:
    request: AskRequest | None = None
    reply: str | None = None


def parse_update(update, owner_id: int) -> BotAction | None:
    if type(update) is not dict or type(update.get("message")) is not dict:
        return None
    message = update["message"]
    sender, chat = message.get("from"), message.get("chat")
    if (
        type(sender) is not dict
        or type(chat) is not dict
        or type(sender.get("id")) is not int
        or sender["id"] != owner_id
        or sender.get("is_bot") is not False
        or type(chat.get("id")) is not int
        or chat["id"] != owner_id
        or chat.get("type") != "private"
        or "forward_origin" in message
        or "via_bot" in message
        or type(message.get("text")) is not str
    ):
        return None
    text = message["text"].strip()
    if len(text) > 512:
        return BotAction(reply=HELP_TEXT)
    if text.startswith("/"):
        command, _, text = text.partition(" ")
        if command.casefold() != "/ask":
            return BotAction(reply=HELP_TEXT)
    try:
        return BotAction(request=AskRequest(query=text))
    except ValidationError:
        return BotAction(reply=HELP_TEXT)


def format_reply(response: AgentResponse) -> list[str]:
    if not response.answer.strip() or len(response.answer) > 12_000 or len(response.citations) > 30:
        raise ValueError("Invalid bot answer size")
    validate_answer_evidence(response.answer, response.citations)
    links = []
    seen = set()
    for citation in response.citations:
        if not re.fullmatch(r"\[\d{1,2}\.\d{1,2}\]", citation.marker) or not re.fullmatch(
            r"(?:\d{4}\.\d{4,5}|[a-z][a-z.-]*/\d{7})(?:v\d+)?", citation.arxiv_id
        ):
            raise ValueError("Invalid bot citation identity")
        if citation.arxiv_id not in seen:
            seen.add(citation.arxiv_id)
            links.append(f"{citation.marker} https://arxiv.org/abs/{citation.arxiv_id}")
    text = response.answer + ("\n\nPapers:\n" + "\n".join(links) if links else "")
    # Count UTF-16 code units conservatively; do not split a Unicode character.
    parts: list[str] = []
    current: list[str] = []
    units = 0
    for char in text:
        width = 2 if ord(char) > 0xFFFF else 1
        if units + width > 4000:
            parts.append("".join(current))
            current, units = [], 0
        current.append(char)
        units += width
    if current:
        parts.append("".join(current))
    return parts
