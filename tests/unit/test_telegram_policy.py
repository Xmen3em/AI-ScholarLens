import json

import pytest
from src.services.telegram_policy import format_reply, parse_update

from tests.unit.test_agent_service import QUESTION, answer, service

OWNER = 123456789


def update(text=QUESTION, **changes):
    value = {
        "update_id": 10,
        "message": {
            "message_id": 1,
            "from": {"id": OWNER, "is_bot": False},
            "chat": {"id": OWNER, "type": "private"},
            "text": text,
        },
    }
    value["message"].update(changes)
    return value


@pytest.mark.parametrize(
    "changes",
    [
        {"from": {"id": OWNER + 1, "is_bot": False}},
        {"from": {"id": OWNER, "is_bot": True}},
        {"from": {"id": True, "is_bot": False}},
        {"chat": {"id": OWNER, "type": "group"}},
        {"chat": {"id": OWNER + 1, "type": "private"}},
        {"forward_origin": {"type": "user"}},
        {"via_bot": {"id": 123}},
        {"text": 1},
    ],
)
def test_nonowner_or_untrusted_message_is_ignored(changes):
    assert parse_update(update(**changes), OWNER) is None


@pytest.mark.parametrize("raw", [None, [], {}, {"edited_message": update()["message"]}, {"message": []}])
def test_malformed_or_other_update_types_are_ignored(raw):
    assert parse_update(raw, OWNER) is None


@pytest.mark.parametrize("text", ["/start", "/help", "/ask", "/unknown", " ", "x" * 501, "/ask " + "x" * 501])
def test_commands_or_invalid_questions_only_return_fixed_help(text):
    action = parse_update(update(text), OWNER)
    assert action is not None and action.request is None and action.reply


@pytest.mark.parametrize("text", [QUESTION, "/ask " + QUESTION])
def test_owner_question_reuses_exact_public_api_request_contract(text):
    action = parse_update(update(text), OWNER)
    assert action.request.query == QUESTION and action.request.top_k == 3 and action.request.use_hybrid
    assert action.request.model is None and action.reply is None


@pytest.mark.anyio
async def test_cited_reply_keeps_validated_answer_and_only_canonical_paper_links():
    response = await answer(service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}]))
    response.sources = ["https://attacker.invalid/private-token"]
    response.citations[0].title = "private title with arbitrary URL https://attacker.invalid"
    replies = format_reply(response)
    result = "\n".join(replies)
    assert response.answer in result and "[1.1]" in result and "https://arxiv.org/abs/" in result
    assert "attacker.invalid" not in result and "private title" not in result
    assert all(len(reply.encode("utf-16-le")) // 2 <= 4000 for reply in replies)


@pytest.mark.anyio
async def test_invalid_response_word_limit_or_citation_identity_is_rejected():
    response = await answer(service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}]))
    for changes in [{"answer": "x " * 201}, {"answer": ""}]:
        with pytest.raises(ValueError):
            format_reply(response.model_copy(update=changes))
    response.citations[0].arxiv_id = "evil/../../private"
    with pytest.raises(ValueError):
        format_reply(response)


@pytest.mark.anyio
async def test_unicode_message_splitting_is_bounded_and_lossless():
    response = await answer(service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}]))
    response.citations[0].evidence = "😀" * 3500
    response.answer = '- "' + response.citations[0].evidence + '" [1.1]'
    parts = format_reply(response)
    assert "".join(parts).startswith(response.answer) and len(parts) == 2
    assert all(len(part.encode("utf-16-le")) // 2 <= 4000 for part in parts)
