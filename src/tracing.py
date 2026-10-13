"""Explicit metadata-only Langfuse OTLP traces; no global auto-instrumentation."""

import functools
import json
import logging
import time
from contextvars import ContextVar

import httpx
from src.operations import request_context
from src.services.hf.registry import REGISTERED_HF_MODELS

logger = logging.getLogger(__name__)
parent_span: ContextVar = ContextVar("operational_parent_span", default=None)

EVENTS = {
    "rag_retrieval", "rag_generation", "rag_selector_retry", "rag_selection_validation_failed",
    "rag_answer_validation_failed", "rag_stream_error", "rag_stream_completed", "rag_stream_interrupted",
    "rag_cache", "rate_limit_store_unavailable", "readiness_failed",
    "agent_stage", "agent_completed", "agent_error", "agent_selector_retry",
    "agent_stream_error", "agent_stream_completed", "agent_stream_interrupted",
    "hf_generation_attempt",
}
NUMBERS = {"duration_ms", "paper_groups", "passages", "load_ns", "prompt_eval_ns", "generation_ns",
           "total_ns", "prompt_tokens", "output_tokens", "attempt", "status", "model_calls", "retrieval_attempts", "stages", "status_code"}
REASONS = {"GroundingError", "OllamaResponseError", "OllamaTimeoutError", "OllamaConnectionError", "ValueError",
           "invalid structured output", "answer selection must contain at most three distinct IDs",
           "answer selection contains an unknown evidence ID", "answer is missing a citation marker",
           "answer contains unknown citation markers", "answer exceeds the 200-word limit",
           "answer must contain only cited evidence excerpts", "answer excerpt does not match its cited passage"}
REASONS |= {"TimeoutError", "AgentBusyError"}
REASONS |= {"HFGenerationError", "HFResponseError", "HFTimeoutError"}
ENUMS = {
    "provider": {"groq", "fireworks-ai"}, "model": REGISTERED_HF_MODELS,
    "mode": {"bm25", "hybrid"}, "method": {"GET", "POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"},
    "outcome": {"completed", "failed", "stream_error", "interrupted", "answered", "abstained", "out_of_scope"},
    "operation": {"validate", "retrieve", "grade", "rewrite", "answer", "abstain"},
    "result": {"hit", "miss", "stored", "unavailable", "invalid", "bypass", "revision_changed"},
    "done_reason": {"stop", "length", "load", "unload", "unknown"},
}


def safe_fields(fields):
    result = {k: v for k, v in fields.items() if k in NUMBERS and isinstance(v, (int, float))}
    result.update({k: v for k, v in fields.items() if k in ENUMS and isinstance(v, str) and v in ENUMS[k]})
    if isinstance(fields.get("rewritten"), bool):
        result["rewritten"] = fields["rewritten"]
    # Failure names are bounded classifications; never serialize exception messages.
    if "reason" in fields:
        result["failure"] = True
        reason = fields["reason"]
        result["reason"] = reason if isinstance(reason, str) and reason in REASONS else "unclassified"
    return result


class LocalTracing:
    def __init__(self, processor):
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.id_generator import RandomIdGenerator

        class RequestIds(RandomIdGenerator):
            def generate_trace_id(self):
                context = request_context.get() or {}
                return int(context["request_id"], 16) if context.get("request_id") else super().generate_trace_id()

        self.provider = TracerProvider(resource=Resource({"service.name": "AI-ScholarLens", "entry_point": "api"}),
                                       id_generator=RequestIds(), shutdown_on_exit=False)
        self.provider.add_span_processor(processor)
        self.tracer = self.provider.get_tracer("scholarlens.operations")

    @classmethod
    def create(cls, settings):
        if not settings.local_tracing_enabled:
            return None
        from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

        class LocalExporter(SpanExporter):
            def export(self, spans):
                try:
                    # No proxy, redirect, retry or implicit OTEL environment destination.
                    with httpx.Client(timeout=0.5, trust_env=False, follow_redirects=False) as client:
                        with client.stream("POST",
                            settings.local_tracing_url.rstrip("/") + "/api/public/otel/v1/traces",
                            content=encode_spans(spans).SerializeToString(),
                            headers={"Content-Type": "application/x-protobuf", "x-langfuse-ingestion-version": "4"},
                            auth=(settings.local_tracing_public_key.get_secret_value(),
                                  settings.local_tracing_secret_key.get_secret_value()),
                        ) as response:
                            if response.status_code == 200:
                                return SpanExportResult.SUCCESS
                except Exception:
                    pass
                logger.warning('Local trace export unavailable')
                return SpanExportResult.FAILURE

        return cls(BatchSpanProcessor(LocalExporter(), max_queue_size=256, max_export_batch_size=32,
                                      schedule_delay_millis=1000, export_timeout_millis=1000))

    def start(self, request_id):
        # Middleware has already installed the server-generated correlation ID.
        return self.tracer.start_span("http_request", attributes={"request_id": request_id, "entry_point": "api"})

    def phase(self, name, start_time=None):
        from opentelemetry.trace import set_span_in_context
        context = request_context.get() or {}
        root = context.get("trace_root")
        if root is None:
            return None
        return self.tracer.start_span(name, context=set_span_in_context(parent_span.get() or root), start_time=start_time,
                                      attributes={"request_id": context["request_id"], "entry_point": "api"})

    def event(self, event, fields):
        if event not in EVENTS:
            return
        ended = time.time_ns()
        duration = fields.get("total_ns") if event == "rag_generation" else None
        span = self.phase(event, start_time=ended - duration if isinstance(duration, int) and duration > 0 else None)
        if span is not None:
            values = safe_fields(fields)
            values["langfuse.observation.type"] = "generation" if event == "rag_generation" else "span"
            if event == "rag_generation":
                usage = {k: values[n] for k, n in [("input", "prompt_tokens"), ("output", "output_tokens")] if n in values}
                span.set_attribute("langfuse.observation.usage_details", json.dumps(usage))
                span.set_attribute("gen_ai.system", "ollama")
            span.set_attributes(values)
            if values.get("failure"):
                from opentelemetry.trace import StatusCode
                span.set_status(StatusCode.ERROR)
            span.end(end_time=ended if isinstance(duration, int) and duration > 0 else None)

    def finish(self, root, fields):
        from opentelemetry.trace import StatusCode
        root.set_attributes(safe_fields(fields))
        root.set_attribute("route", fields["route"])
        if fields["outcome"] != "completed" or fields["status"] >= 400:
            root.set_status(StatusCode.ERROR)
        root.end()

    def flush(self, timeout_ms=1000):
        return self.provider.force_flush(timeout_millis=timeout_ms)

    def close(self):
        self.provider.shutdown()


def traced(name):
    """Measure async phases, marking failures without capturing exception content."""
    def decorate(function):
        @functools.wraps(function)
        async def wrapped(*args, **kwargs):
            context = request_context.get() or {}
            trace = context.get("tracing")
            span = None
            try:
                span = trace.phase(name) if trace else None
            except Exception:
                pass
            token = parent_span.set(span)
            started = time.perf_counter()
            failed = False
            try:
                return await function(*args, **kwargs)
            except BaseException:
                failed = True
                raise
            finally:
                parent_span.reset(token)
                if span is not None:
                    try:
                        from opentelemetry.trace import StatusCode
                        span.set_attribute("duration_ms", (time.perf_counter() - started) * 1000)
                        if failed:
                            span.set_status(StatusCode.ERROR)
                        span.end()
                    except Exception:
                        pass
        return wrapped
    return decorate
