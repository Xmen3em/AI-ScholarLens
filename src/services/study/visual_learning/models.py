"""Bounded data contracts; scientific display content comes from a reviewed catalog."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

MAX_SPEC_BYTES = 16 * 1024
Phase = Literal["inference", "training"]
Visibility = Literal["inference", "training", "both"]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
FactRefs = Annotated[list[Identifier], Field(min_length=1, max_length=6)]


class VisualError(ValueError):
    """Finite public category, never arbitrary model/source content."""


def safe_display(value: str) -> str:
    # Joiners/diacritics are meaningful; do not strip all Unicode format characters.
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]", value):
        raise ValueError("unexpected_display_control")
    return value


DisplayText = Annotated[str, Field(min_length=1, max_length=640), AfterValidator(safe_display)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class TextRun(StrictModel):
    text: DisplayText
    direction: Literal["rtl", "ltr", "auto"]


Runs = Annotated[list[TextRun], Field(min_length=1, max_length=12)]


class SourceIdentity(StrictModel):
    paper_id: str = Field(pattern=r"^\d{4}\.\d{4,5}v[1-9]\d{0,3}$", max_length=48)
    title: DisplayText
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_revision: str = Field(min_length=1, max_length=80)

    @property
    def url(self) -> str:
        return "https://arxiv.org/pdf/" + self.paper_id


class SourceExcerpt(StrictModel):
    id: Identifier
    block_id: str = Field(pattern=r"^p\d+b\d+$", max_length=32)
    page: int = Field(ge=1, le=45)
    section: DisplayText
    quote: str = Field(min_length=1, max_length=450)


class EvidenceFact(StrictModel):
    id: Identifier
    statement_ar: DisplayText
    evidence_ids: FactRefs
    verification: Literal["source_checked"]


class VisualNode(StrictModel):
    id: Identifier
    label_ar: Annotated[str, Field(min_length=1, max_length=60), AfterValidator(safe_display)]
    term_en: Annotated[str, Field(min_length=1, max_length=80), AfterValidator(safe_display)]
    phase: Visibility
    fact_ids: FactRefs
    details: Runs


class VisualEdge(StrictModel):
    id: Identifier
    source: Identifier
    target: Identifier
    relation: Literal["data_flow", "parameter_update", "preparation", "marginalize"]
    phase: Visibility
    label_ar: DisplayText
    fact_ids: FactRefs


class VisualStep(StrictModel):
    id: Identifier
    phase: Phase
    heading_ar: DisplayText
    body: Runs
    node_ids: Annotated[list[Identifier], Field(min_length=1, max_length=12)]
    edge_ids: Annotated[list[Identifier], Field(max_length=24)]
    fact_ids: FactRefs


class VisualSpec(StrictModel):
    schema_version: Literal[1] = 1
    template: Literal["method_flow"] = "method_flow"
    language: Literal["ar-EG"] = "ar-EG"
    catalog_revision: str = Field(min_length=1, max_length=80)
    source: SourceIdentity
    title_ar: DisplayText
    nodes: Annotated[list[VisualNode], Field(min_length=1, max_length=12)]
    edges: Annotated[list[VisualEdge], Field(max_length=24)]
    steps: Annotated[list[VisualStep], Field(min_length=1, max_length=8)]


class ReviewedComparison(StrictModel):
    dataset: str
    split: str
    metric: str
    page: int = Field(ge=1, le=45)
    block_id: str
    values: dict[str, float] = Field(min_length=2, max_length=12)


class RejectedClaim(StrictModel):
    id: Identifier
    reason: DisplayText


class CuratedMethod(StrictModel):
    revision: str = Field(min_length=1, max_length=80)
    source: SourceIdentity
    title_ar: DisplayText
    scope_notice: DisplayText
    evidence: Annotated[list[SourceExcerpt], Field(min_length=1, max_length=24)]
    facts: Annotated[list[EvidenceFact], Field(min_length=1, max_length=24)]
    training_policy: dict[Identifier, Literal["fixed", "updated"]] = Field(min_length=4, max_length=4)
    token_unit: Literal["token"]
    reviewed_comparison: ReviewedComparison
    rejected_claims: Annotated[list[RejectedClaim], Field(min_length=3, max_length=3)]
    nodes: Annotated[list[VisualNode], Field(min_length=1, max_length=12)]
    edges: Annotated[list[VisualEdge], Field(max_length=24)]
    steps: Annotated[list[VisualStep], Field(min_length=1, max_length=8)]
