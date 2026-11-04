"""Authenticated local study endpoints; owner identity comes from startup config.

With the multi-user beta installed (docs/specs/multi-user.md), each message carries the
Telegram user it came from, passes the access gate, and reaches that student's own service.
"""

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from src.services.study import access_text
from src.services.study.access import CAIRO, AccessGate
from src.services.study.registry import ServiceRegistry
from src.services.study.service import BUSY, HELP
from src.services.study.store import StudyStore, pending_deliveries_all

USER_ID = Field(default=None, ge=1, lt=2**52)
# A lesson or answer is a writer call and a check call; /deep is two research calls and a check.
CALLS = {"/deep": 4}
DEFAULT_CALLS = 2


class StudyMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    intent: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=512)
    user_id: int | None = USER_ID


class DeliveryClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    job_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    user_id: int | None = USER_ID


class Undeliverable(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    user_id: int = Field(ge=1, lt=2**52)


def install_multi_user(app: FastAPI, gate: AccessGate, registry: ServiceRegistry, path: Path, owner_id: int) -> None:
    app.state.gate, app.state.registry, app.state.study_path, app.state.owner_id = gate, registry, path, owner_id


def _multi(app: FastAPI) -> bool:
    return getattr(app.state, "registry", None) is not None


def _owner_command(app: FastAPI, command: str, argument: str) -> str | None:
    gate: AccessGate = app.state.gate
    if command == "/invite":
        try:
            count = int(argument) if argument.strip() else 1
            codes = gate.create_invites(count)
        except ValueError:
            return access_text.INVITE_HOW
        return access_text.INVITES.format(codes="\n".join(codes))
    if command == "/members":
        lines = []
        for member in gate.members():
            if member["revoked"]:
                continue
            today = gate.day_usage(member["user"])
            active = datetime.fromtimestamp(member["last_active"], CAIRO).strftime("%Y-%m-%d %H:%M")
            lines.append(access_text.MEMBER_LINE.format(user=member["user"], role=member["role"], last_active=active, **today))
        return "\n".join(lines)
    if command == "/usage":
        usage = gate.owner_usage()
        lines = [access_text.OWNER_USAGE.format(**usage)] + [access_text.OWNER_TOP.format(**row) for row in usage["top"]]
        return "\n".join(lines)
    return None


async def _revoke(app: FastAPI, argument: str) -> str:
    if not argument.strip().isdecimal():
        return access_text.REVOKE_HOW
    user = int(argument)
    if not app.state.gate.revoke(user):
        return access_text.NO_SUCH_MEMBER
    await app.state.registry.forget(user)
    return access_text.REVOKE_DONE.format(user=user)


async def _multi_message(app: FastAPI, request: StudyMessage) -> dict:
    gate: AccessGate = app.state.gate
    registry: ServiceRegistry = app.state.registry
    user, text = request.user_id, request.text.strip()
    assert user is not None
    if not gate.allow_message(user):
        return {"reply": access_text.TOO_FAST}
    command, _, argument = text.partition(" ")
    command = command.lower()
    role = gate.role(user)
    if role is None:
        if command == "/start" and argument.strip():
            return {"reply": access_text.WELCOME if gate.redeem(user, argument) else access_text.BAD_CODE}
        revoked = gate.is_revoked(user)
        if gate.note_once(user, "revoked" if revoked else "not_member"):
            return {"reply": access_text.REVOKED if revoked else access_text.NOT_MEMBER}
        return {"reply": None}
    gate.touch(user)
    if command == "/start" and argument.strip():
        return {"reply": access_text.WELCOME}
    if command == "/privacy":
        return {"reply": access_text.PRIVACY}
    if command in {"/help", "/start"}:
        lines = access_text.STUDENT_HELP_LINES + (access_text.OWNER_HELP_LINES if role == "owner" else ())
        return {"reply": HELP + "\n" + "\n".join(lines)}
    if role == "owner":
        if command == "/revoke":
            return {"reply": await _revoke(app, argument)}
        reply = _owner_command(app, command, argument)
        if reply is not None:
            return {"reply": reply}
    elif command == "/usage":
        left = gate.usage(user)
        settings = gate.settings
        return {"reply": access_text.USAGE.format(p=left["papers_left"], P=settings.daily_papers,
                                                  q=left["questions_left"], Q=settings.daily_questions)}
    elif command == "/deep":
        return {"reply": access_text.DEEP_OWNER_ONLY}
    service = registry.service(user)
    kind = service.request_kind(text)
    # Commands that never call the model (/forget, /study, /notes, /level, title search) reserve
    # nothing and keep the service's own replies, including /forget's refusal while a job runs.
    calls = 0 if kind == "other" else CALLS.get(command, DEFAULT_CALLS)
    if calls and registry.busy(user):
        return {"reply": BUSY}
    key = f"{user}:{request.intent}"
    refusal = gate.admit(user, kind, key, calls)
    if refusal is not None:
        return {"reply": refusal}
    result = service.submit(request.intent, text)
    if result.get("fallback") is True and role != "owner":
        gate.release(key)
        return {"reply": access_text.NO_PAPER_YET}
    if "job_id" in result and registry.track(user, result["job_id"]):
        gate.bind(key, result["job_id"])
    else:
        gate.release(key)
    return result


def add_study_routes(app: FastAPI) -> None:
    @app.post("/api/v1/study/messages")
    async def message(request: StudyMessage):
        if _multi(app):
            if request.user_id is None:
                raise HTTPException(status_code=422, detail="user_id is required")
            return await _multi_message(app, request)
        if request.user_id is not None:
            raise HTTPException(status_code=422, detail="user_id is not accepted")
        if getattr(app.state, "legacy_question_busy", False):
            return {"reply": BUSY}
        return app.state.study.submit(request.intent, request.text)

    @app.post("/api/v1/study/pending")
    async def pending():
        if _multi(app):
            jobs = pending_deliveries_all(app.state.study_path)
            return {"jobs": [{"id": row["id"], "status": row["status"], "user": int(row["owner"])} for row in jobs],
                    "running": app.state.registry.running()[:15]}
        study = app.state.study
        return {"jobs": [{"id": row["id"], "status": row["status"]} for row in study.store.pending_deliveries()],
                "running": [{"id": job_id, "stage": stage} for job_id, stage in list(study.progress.items())[:5]]}

    @app.post("/api/v1/study/claim")
    async def claim(request: DeliveryClaim):
        if _multi(app):
            if request.user_id is None:
                raise HTTPException(status_code=422, detail="user_id is required")
            store = StudyStore(app.state.study_path, str(request.user_id))
        else:
            if request.user_id is not None:
                raise HTTPException(status_code=422, detail="user_id is not accepted")
            store = app.state.study.store
        job = store.get_job(request.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Study job not found")
        if not store.claim_delivery(request.job_id):
            return {"claimed": False}
        return {"claimed": True, "result": job["result"] or {"text": "الطلب اتوقف ومش هيتعاد تلقائيًا."}}

    @app.post("/api/v1/study/undeliverable")
    async def undeliverable(request: Undeliverable):
        if not _multi(app):
            raise HTTPException(status_code=404, detail="Not found")
        app.state.gate.mark_inactive(request.user_id)
        return {"ok": True}
