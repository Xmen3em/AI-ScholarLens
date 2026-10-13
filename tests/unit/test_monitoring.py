import json
import logging

from src.monitoring import attach_monitoring, summarize, write_report
from src.operations import emit_event, request_context


def test_report_counts_failures_quotas_usage_and_percentiles(writable_cache_dir):
    events = [dict(event='http_request_completed', route='/api/v1/ask', status=status, outcome=outcome,
                   duration_ms=duration, timestamp=10)
              for status, outcome, duration in [(200, 'completed', 10), (200, 'stream_error', 100), (429, 'completed', 30)]]
    events += [dict(event='rag_generation', prompt_tokens=12, output_tokens=3, generation_ns=500000000,
                    timestamp=10), dict(event='rag_selector_retry', timestamp=10),
               dict(event='rag_cache', result='hit', timestamp=10), dict(event='rag_cache', result='miss', timestamp=10)]
    result = summarize(events)
    assert result['requests'] == 3
    assert result['failures'] == 1
    assert result['quota_rejections'] == 1
    assert result['retries'] == 1
    assert result['usage']['prompt_tokens'] == 12
    assert result['cache_hit_rate'] == 0.5
    assert result['latency']['/api/v1/ask']['p50_ms'] == 30
    assert result['latency']['/api/v1/ask']['p95_ms'] == 100
    report = writable_cache_dir / 'monitor.html'
    write_report(result, report)
    assert 'Ollama' in report.read_text(encoding='utf-8')
    assert 'p95' in report.read_text(encoding='utf-8')


def test_local_rotating_files_export_allowlisted_metadata(writable_cache_dir):
    logger = logging.getLogger('src.operations')
    previous = logger.level
    logger.setLevel(logging.INFO)
    handler = attach_monitoring(str(writable_cache_dir))
    token = request_context.set({'request_id': 'c' * 32})
    try:
        emit_event('rag_generation', prompt_tokens=7, answer='private answer', query='private query',
                   reason='private exception', key='private key')
        handler.flush()
        data = [json.loads(line) for path in writable_cache_dir.glob('events-*.jsonl') for line in path.read_text().splitlines()]
        assert data[0]['request_id'] == 'c' * 32
        assert data[0]['prompt_tokens'] == 7
        assert 'private' not in json.dumps(data)
        assert handler.maxBytes == 1048576 and handler.backupCount == 3
    finally:
        request_context.reset(token)
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous)
