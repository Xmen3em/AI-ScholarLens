"""Authenticated local study endpoints; owner identity comes from startup config."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class StudyMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    intent: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=512)


class DeliveryClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    job_id: str = Field(pattern=r"^[a-f0-9]{32}$")


def add_study_routes(app: FastAPI) -> None:
    @app.post("/api/v1/study/messages")
    async def message(request: StudyMessage):
        return app.state.study.submit(request.intent, request.text)

    @app.post("/api/v1/study/pending")
    async def pending():
        return {"jobs": [{"id": row["id"], "status": row["status"]} for row in app.state.study.store.pending_deliveries()]}

    @app.post("/api/v1/study/claim")
    async def claim(request: DeliveryClaim):
        store = app.state.study.store
        job = store.get_job(request.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Study job not found")
        if not store.claim_delivery(request.job_id):
            return {"claimed": False}
        return {"claimed": True, "result": job["result"] or {"text": "الطلب اتوقف ومش هيتعاد تلقائيًا."}}
