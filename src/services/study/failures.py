"""Finite failure categories shared across the private worker boundary."""

SAFE_FAILURES = frozenset({
    "study_generation_unavailable", "research_unavailable_or_invalid", "lesson_validation_failed",
    "review_validation_failed", "study_memory_unavailable", "study_context_limit", "study_model_busy",
    "study_response_limit", "study_response_invalid_or_unavailable", "one_output_contract_required",
    "research_environment_required", "research_output_limit", "research_worker_failed", "research_output_invalid",
    "research_worker_timeout", "research_worker_unavailable",
    "research_tool_call_rejected", "research_tool_allowlist_violation", "research_tool_execution_denied",
    "study_stop_override_not_supported", "study_requires_text_messages", "unsupported_study_role",
    "invalid_tool_arguments", "invalid_study_search", "invalid_block_request", "unknown_evidence_block",
    "study_tool_budget_exhausted", "active_paper_required", "admitted_research_job_required",
    "attempt_budget_exhausted", "run_attempt_budget_exhausted", "research_final_json_invalid",
    *{f"study_provider_http_{code}" for code in (400, 401, 402, 403, 404, 408, 413, 422, 429, 500, 502, 503, 504)},
})
SAFE_DIAGNOSTICS = SAFE_FAILURES | frozenset({
    "shape", "missing_evidence", "unsupported_quote", "unsupported_number", "arabic_output_required", "semantic_support",
    "ValueError", "TypeError", "KeyError", "TimeoutError", "JSONDecodeError", "ValidationError",
    "NotImplementedError", "RuntimeError", "StoreConflict", "OSError",
})
# Where a Deep job stopped: worker phases, then the parent's process boundary.
SAFE_STAGES = frozenset({
    "settings", "admission", "source", "agent", "final_json", "validation",
    "worker_start", "worker_timeout", "worker_output", "worker_exit",
})


def failure_payload(exc: Exception, *, default: str = "research_unavailable_or_invalid") -> dict[str, str]:
    # Never serialize arbitrary exception messages, model output or tool arguments.
    message = str(exc)
    code = message if message in SAFE_FAILURES else default
    detail = getattr(exc, "diagnostic", None)
    if type(detail) is not str or detail not in SAFE_DIAGNOSTICS:
        detail = code if code in SAFE_FAILURES and code != default else type(exc).__name__
    result = {"error": code}
    if detail in SAFE_DIAGNOSTICS:
        result["diagnostic"] = detail
    stage = getattr(exc, "stage", None)
    if type(stage) is str and stage in SAFE_STAGES:
        result["stage"] = stage
    return result


def staged(exc: Exception, stage: str) -> Exception:
    # Keep the first (innermost) stage; an outer handler must not relabel it.
    if getattr(exc, "stage", None) is None:
        exc.stage = stage  # type: ignore[attr-defined]
    return exc
