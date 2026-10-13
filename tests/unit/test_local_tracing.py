import json
import logging
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import ValidationError
from src.config import Settings
from src.middlewares import OperationalMiddleware
from src.operations import emit_event
from src.tracing import LocalTracing, traced


def settings(tmp_path, **extra):
    return Settings(_env_file=None, api_rate_limit_path=str(tmp_path / 'limits'), **extra)


def test_tracing_is_disabled_and_cloud_is_rejected(tmp_path):
    assert LocalTracing.create(settings(tmp_path)) is None
    with pytest.raises(ValidationError):
        settings(tmp_path, local_tracing_enabled=True, local_tracing_url='https://cloud.langfuse.com')


@pytest.mark.anyio
async def test_request_and_phases_correlate_without_content(tmp_path, caplog):
    exporter = InMemorySpanExporter()
    trace = LocalTracing(SimpleSpanProcessor(exporter))
    app = FastAPI()
    app.state.tracing = trace
    app.add_middleware(OperationalMiddleware, settings=settings(tmp_path))

    @traced('retrieval')
    async def retrieve():
        emit_event('rag_retrieval', duration_ms=12, mode='bm25', query='private question', evidence='private evidence')

    @app.get('/ok')
    async def ok():
        await retrieve()
        emit_event('rag_generation', prompt_tokens=12, output_tokens=3, generation_ns=1000000)
        return {'answer': 'private answer'}

    @app.get('/broken')
    async def broken():
        raise RuntimeError('private exception')

    caplog.set_level(logging.INFO)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        good = await client.get('/ok?secret=secret')
        bad = await client.get('/broken')
    spans = exporter.get_finished_spans()
    root = next(s for s in spans if s.name == 'http_request' and s.attributes['status'] == 200)
    assert format(root.context.trace_id, '032x') == good.headers['x-request-id']
    assert all(s.context.trace_id == root.context.trace_id for s in spans if s.name != 'http_request')
    assert any(s.name == 'retrieval' and s.parent.span_id == root.context.span_id for s in spans)
    assert any(s.name == 'rag_generation' and s.attributes['prompt_tokens'] == 12 for s in spans)
    assert bad.status_code == 500
    assert any(s.attributes.get('outcome') == 'failed' for s in spans)
    exported = json.dumps([dict(s.attributes) for s in spans])
    assert not any(x in exported for x in ['private', 'secret', 'exception'])
    trace.close()


def test_export_failure_is_bounded_and_does_not_raise(tmp_path):
    config = settings(tmp_path, local_tracing_enabled=True,
                      local_tracing_public_key='test-public', local_tracing_secret_key='test-secret',
                      local_tracing_url='http://127.0.0.1:1')
    trace = LocalTracing.create(config)
    started = time.monotonic()
    root = trace.start('a' * 32)
    trace.finish(root, {'status': 200, 'outcome': 'completed', 'route': '/ok', 'method': 'GET'})
    assert time.monotonic() - started < 0.1
    assert trace.flush(1000)
    trace.close()
    assert time.monotonic() - started < 2


@pytest.mark.anyio
async def test_real_otlp_payload_on_loopback_has_only_metadata(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    payloads = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == '/api/public/otel/v1/traces'
            assert self.headers['x-langfuse-ingestion-version'] == '4'
            payloads.append(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    trace = LocalTracing.create(settings(
        tmp_path, local_tracing_enabled=True, local_tracing_public_key='test-public',
        local_tracing_secret_key='test-secret', local_tracing_url=f'http://127.0.0.1:{server.server_port}',
    ))
    app = FastAPI()
    app.state.tracing = trace
    app.add_middleware(OperationalMiddleware, settings=settings(tmp_path))

    @app.post('/ask')
    async def route():
        emit_event('rag_generation', output_tokens=7, answer='private answer', prompt='private prompt')
        return {'answer': 'private answer'}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/ask', json={'query': 'private question'})
        assert trace.flush(1500)
        decoded = [ExportTraceServiceRequest.FromString(p) for p in payloads]
        spans = [s for p in decoded for resource in p.resource_spans for scope in resource.scope_spans for s in scope.spans]
        assert {s.name for s in spans} == {'http_request', 'rag_generation'}
        assert {s.trace_id.hex() for s in spans} == {response.headers['x-request-id']}
        assert all(s.end_time_unix_nano >= s.start_time_unix_nano for s in spans)
        assert all(b'private' not in p and b'test-secret' not in p for p in payloads)
    finally:
        trace.close()
        server.shutdown()
        server.server_close()


@pytest.mark.anyio
async def test_stream_close_is_correlated_and_marked_interrupted(tmp_path):
    from types import SimpleNamespace

    from src.operations import request_context
    from src.routers.ask import _events
    from src.schemas.api.rag import SourcesEvent

    exporter = InMemorySpanExporter()
    trace = LocalTracing(SimpleSpanProcessor(exporter))
    context = {'request_id': 'b' * 32, 'tracing': trace}
    token = request_context.set(context)
    context['trace_root'] = trace.start(context['request_id'])
    prepared = SimpleNamespace(sources_event=lambda: SourcesEvent(query='private', sources=[], citations=[],
                               chunks_used=0, search_mode='bm25', model='model'),
                               context=SimpleNamespace(citations=[]))
    events = _events(prepared, None)
    try:
        assert (await anext(events)).startswith('event: sources')
        await events.aclose()
        assert context['stream_interrupted']
        assert any(s.name == 'rag_stream_interrupted' for s in exporter.get_finished_spans())
    finally:
        trace.finish(context['trace_root'], {'status': 200, 'route': '/stream', 'outcome': 'interrupted'})
        request_context.reset(token)
        trace.close()
