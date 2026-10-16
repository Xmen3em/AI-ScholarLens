"""Separate model-knowledge explanations from source-validated paper answers."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def explanation_text(value: str) -> str:
    value = value.strip()
    if not value or len(value.split()) > 200:
        raise ValueError("Explanation must contain at most 200 words")
    if re.search(r"https?://|\[\d+(?:\.\d+)?\]|\barxiv\b|\bdoi:", value, re.IGNORECASE):
        raise ValueError("Model-knowledge explanations cannot claim paper citations")
    return value


class LearningDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    kind: Literal["general", "paper", "clarification", "out_of_scope"]
    explanation: str = Field(max_length=2400)

    @model_validator(mode="after")
    def validate_kind(self):
        if self.kind in {"general", "clarification"}:
            self.explanation = explanation_text(self.explanation)
        elif self.explanation:
            raise ValueError("Paper and out-of-scope routes must not generate an answer")
        return self


class LearningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    kind: Literal["general_explanation", "clarification", "out_of_scope"]
    query: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=2400)
    model: Literal["openai/gpt-oss-120b:cerebras"]
    model_calls: Literal[1] = 1

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value):
        return explanation_text(value)
