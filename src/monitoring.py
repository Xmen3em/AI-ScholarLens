"""Bounded per-worker event files and offline operational summaries."""

import argparse
import html
import json
import logging
import math
import os
from collections import Counter, defaultdict
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.tracing import EVENTS, safe_fields


class MetadataEvents(RotatingFileHandler):
    def emit(self, record):
        try:
            event = json.loads(record.getMessage())
            name = event.get("event")
            if name not in EVENTS | {"http_request_completed"}:
                return
            safe = {"event": name, "timestamp": record.created, "entry_point": "api",
                    "request_id": event.get("request_id"), **safe_fields(event)}
            if name == "http_request_completed":
                safe["route"] = event["route"]  # Server-owned route template, never a raw URL.
            copy = logging.makeLogRecord({**record.__dict__, "msg": json.dumps(safe), "args": ()})
            super().emit(copy)
        except Exception:
            pass  # A full/unwritable monitoring disk must not affect API responses.


def attach_monitoring(directory):
    if not directory:
        return None
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    handler = MetadataEvents(path / f"events-{os.getpid()}.jsonl", maxBytes=1048576, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger("src.operations").addHandler(handler)
    return handler


def summarize(events):
    counts = Counter()
    cache = Counter()
    latencies = defaultdict(list)
    usage = Counter()
    timestamps = []
    for event in events:
        counts[event["event"]] += 1
        if event.get("timestamp") is not None:
            timestamps.append(event["timestamp"])
        if event["event"] == "http_request_completed":
            latencies[event["route"]].append(event["duration_ms"])
            counts["failures"] += int(event["status"] >= 500 or event["outcome"] in {"failed", "stream_error", "interrupted"})
            counts["quota_rejections"] += int(event["status"] == 429)
            counts["auth_rejections"] += int(event["status"] == 401)
        elif event["event"] == "rag_cache":
            cache[event["result"]] += 1
        elif event["event"] == "rag_generation":
            for key in ["prompt_tokens", "output_tokens", "total_ns", "generation_ns", "prompt_eval_ns", "load_ns"]:
                usage[key] += event.get(key) or 0
    def percentiles(values):
        ordered = sorted(values)
        return {"samples": len(ordered), **{f"p{p}_ms": ordered[max(0, math.ceil(len(ordered) * p / 100) - 1)]
                                           for p in [50, 95, 99]}}
    requests = counts["http_request_completed"]
    lookups = cache["hit"] + cache["miss"]
    return {"requests": requests, "failures": counts["failures"], "quota_rejections": counts["quota_rejections"],
            "auth_rejections": counts["auth_rejections"], "failure_rate": counts["failures"] / requests if requests else None,
            "retries": counts["rag_selector_retry"] + counts["agent_selector_retry"],
            "validation_failures": counts["rag_selection_validation_failed"] + counts["rag_answer_validation_failed"],
            "latency": {route: percentiles(values) for route, values in sorted(latencies.items())},
            "usage": dict(usage), "cache": dict(cache), "cache_hit_rate": cache["hit"] / lookups if lookups else None,
            "events": dict(counts), "first_timestamp": min(timestamps) if timestamps else None,
            "last_timestamp": max(timestamps) if timestamps else None}


def read_events(paths, since=None):
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                    if since is None or event.get("timestamp", 0) >= since:
                        yield event
                except (ValueError, TypeError):
                    continue  # Tolerate a trailing line while a worker is writing.


def write_report(summary, destination):
    def table(rows):
        return '<table>' + ''.join('<tr>' + ''.join(f'<td>{html.escape(str(cell))}</td>' for cell in row) + '</tr>'
                                  for row in rows) + '</table>'
    request_rows = [(key.replace('_', ' '), summary[key]) for key in ["requests", "failures", "failure_rate",
                    "quota_rejections", "auth_rejections", "retries", "validation_failures", "cache_hit_rate"]]
    latency_rows = [("Route", "Samples", "p50 ms", "p95 ms", "p99 ms")]
    latency_rows += [(route, stats['samples'], stats['p50_ms'], stats['p95_ms'], stats['p99_ms'])
                     for route, stats in summary['latency'].items()]
    content = '<!doctype html><html lang="en"><meta charset="utf-8"><title>ScholarLens local monitoring</title>'
    content += '<style>body{font:16px system-ui;max-width:1000px;margin:40px auto;color:#173044;padding:0 20px}'
    content += 'table{border-collapse:collapse;width:100%;margin:16px 0}td{padding:10px;border-bottom:1px solid #ddd}'
    content += 'h1,h2{color:#124a65}</style><h1>ScholarLens local monitoring</h1>'
    content += '<p>Snapshot of retained local metadata events. Percentiles use nearest rank; small samples are descriptive.</p>'
    content += '<h2>Requests and failures</h2>' + table(request_rows)
    content += '<h2>Full response latency</h2>' + table(latency_rows)
    content += '<h2>Local Ollama usage</h2><p>Actual tokens and nanosecond durations, including retry attempts. '
    content += 'No billed provider cost is estimated. Cached requests add no generation tokens.</p>' + table(summary['usage'].items())
    content += '<h2>Cache outcomes</h2><p>Hit rate = hits / (hits + misses); bypasses and unavailable lookups are separate.</p>'
    content += table(summary['cache'].items())
    content += '<p>Event window (Unix seconds): ' + html.escape(str((summary['first_timestamp'], summary['last_timestamp']))) + '</p></html>'
    destination.write_text(content, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--since', type=float, help='Include events at or after this Unix timestamp')
    args = parser.parse_args()
    paths = sorted(args.directory.glob('events-*.jsonl*'))
    if not paths:
        parser.error('No local event files found')
    if args.output.exists() or args.output.with_suffix('.json').exists():
        parser.error('Use a new report path to preserve prior evidence')
    result = summarize(read_events(paths, args.since))
    write_report(result, args.output)
    args.output.with_suffix('.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
