"""Bounded public agent metadata and strict internal controller outputs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.schemas.api.rag import AskResponse

Operation = Literal["validate", "retrieve", "grade", "rewrite", "answer", "abstain"]
AgentOutcome = Literal["answered", "abstained", "out_of_scope"]
AGENT_POLICY_VERSION: Literal["bounded-agent-v1"] = "bounded-agent-v1"


class AgentStatus(BaseModel):
    operation: Operation
    attempt: int = Field(ge=0, le=2)


class AgentResponse(AskResponse):
    policy_version: Literal["bounded-agent-v1"] = AGENT_POLICY_VERSION
    outcome: AgentOutcome
    retrieval_attempts: int = Field(ge=0, le=2)
    model_calls: int = Field(ge=0, le=6, description="Generation calls; hybrid retrieval may also embed one query per attempt")
    rewritten: bool
    steps: list[Operation] = Field(max_length=8)


class ScopeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    in_scope: bool


class RelevanceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    relevant_markers: list[str] = Field(max_length=30)


class RewriteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty rewrite")
        return value.strip()
