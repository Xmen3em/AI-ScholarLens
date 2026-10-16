"""Signed exact-match results; revision failures bypass caching, never access controls."""

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path

import anyio
import httpx
from src.commands.backup import FINGERPRINT_SQL
from src.config import Settings
from src.operations import emit_event
from src.schemas.api.rag import AskRequest, AskResponse
from src.services.ollama.client import normalize_model_name
from src.services.rag.context import validate_answer_evidence


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def cache_policy_digest() -> str:
    root = Path(__file__).parent
    files = ["services/rag/service.py", "services/rag/context.py", "services/rag/excerpts.py",
             "services/ollama/prompts/rag_system.txt", "services/search.py", "search/query.py", "search/fusion.py",
             "services/embeddings/ollama.py", "schemas/api/rag.py", "answer_cache.py"]
    return hashlib.sha256(canonical({f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in files}).encode()).hexdigest()


@dataclass(frozen=True)
class CacheTicket:
    request: AskRequest
    key: str | None = None
    revision: dict | None = None
    response: AskResponse | None = None


class AnswerCache:
    def __init__(self, redis, identity, settings: Settings):
        self.redis, self.identity, self.settings = redis, identity, settings
        if settings.api_key is None:
            raise ValueError("Cache signing requires a configured API key")
        self.secret = settings.api_key.get_secret_value().encode()
        self.policy = cache_policy_digest()

    def signature(self, purpose, payload):
        return hmac.new(self.secret, (purpose + payload).encode(), hashlib.sha256).hexdigest()

    def key(self, request, revision):
        controls = request.model_dump()
        controls["model"] = normalize_model_name(request.model or self.settings.ollama_default_model)
        payload = canonical({"request": controls, "revision": revision, "policy": self.policy,
                             "settings": {k: getattr(self.settings, k) for k in ["ollama_models", "ollama_embedding_model",
                                          "rag_sentence_candidates_per_passage", "rag_max_sentence_candidates",
                                          "ollama_timeout"]}})
        return "scholarlens:answer:v1:" + self.signature("key:", payload)

    async def lookup(self, request: AskRequest) -> CacheTicket:
        # Preserve model rejection even if Redis happens to contain a matching value.
        if request.model is not None and request.model not in self.settings.ollama_models:
            return CacheTicket(request)
        try:
            with anyio.fail_after(2):
                revision = await self.identity()
                key = self.key(request, revision)
                raw = await self.redis.get(key)
            ticket = CacheTicket(request, key, revision)
            if raw is None:
                emit_event("rag_cache", result="miss")
                return ticket
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if len(raw.encode()) > 131072:
                raise ValueError("oversized cache entry")
            envelope = json.loads(raw)
            payload = envelope["payload"]
            if not hmac.compare_digest(envelope["signature"], self.signature("value:" + key + ":", payload)):
                raise ValueError("untrusted cache entry")
            response = AskResponse.model_validate_json(payload)
            self.validate(request, response)
            with anyio.fail_after(2):
                if revision != await self.identity():
                    emit_event("rag_cache", result="revision_changed")
                    return CacheTicket(request)
            emit_event("rag_cache", result="hit")
            return CacheTicket(request, key, revision, response)
        except (ValueError, KeyError, TypeError):
            emit_event("rag_cache", result="invalid")
        except Exception:
            emit_event("rag_cache", result="unavailable")
        return CacheTicket(request)

    def validate(self, request, response):
        expected_mode = "hybrid" if request.use_hybrid else "bm25"
        expected_model = request.model or self.settings.ollama_default_model
        if (response.query != request.query or response.model != expected_model or response.search_mode != expected_mode
                or response.chunks_used != len(response.citations)):
            raise ValueError("cache controls mismatch or degraded retrieval")
        validate_answer_evidence(response.answer, response.citations)

    async def store(self, ticket: CacheTicket, response: AskResponse):
        if ticket.key is None:
            return
        try:
            self.validate(ticket.request, response)
            with anyio.fail_after(2):
                if await self.identity() != ticket.revision:
                    emit_event("rag_cache", result="revision_changed")
                    return
                payload = response.model_dump_json()
                if len(payload.encode()) > 120000:
                    emit_event("rag_cache", result="bypass")
                    return
                envelope = canonical({"payload": payload, "signature": self.signature("value:" + ticket.key + ":", payload)})
                if len(envelope.encode()) > 131072:
                    emit_event("rag_cache", result="bypass")
                    return
                await self.redis.set(ticket.key, envelope, ex=self.settings.answer_cache_ttl_seconds)
            emit_event("rag_cache", result="stored")
        except ValueError:
            emit_event("rag_cache", result="bypass")
        except Exception:
            emit_event("rag_cache", result="unavailable")

    async def close(self):
        await self.redis.aclose()
        await self.identity.close()


class ResourceIdentity:
    """Read-only live corpus, searchable index revision and installed model checks."""
    def __init__(self, settings):
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=0.4, trust_env=False, follow_redirects=False)

    def corpus(self):
        import psycopg2
        from sqlalchemy.engine import make_url
        url = make_url(self.settings.postgres_database_url)
        if url.host not in {"localhost", "127.0.0.1", "::1", "postgres"}:
            raise ValueError("Corpus identity must remain local")
        connection = psycopg2.connect(host=url.host, port=url.port or 5432, dbname=url.database,
                                      user=url.username, password=url.password, connect_timeout=1,
                                      options="-c statement_timeout=500 -c default_transaction_read_only=on")
        try:
            with connection.cursor() as cursor:
                cursor.execute(FINGERPRINT_SQL)
                return cursor.fetchone()[0]
        finally:
            connection.close()

    async def get(self, origin, path):
        response = await self.http.get(origin.rstrip("/") + path)
        response.raise_for_status()
        return response.json()

    async def __call__(self):
        # Refresh counters alone invalidate on idle background refreshes. Searchable
        # segment generations + primary sequence numbers detect visibility and writes.
        index = self.settings.opensearch_host
        metadata = await self.get(index, "/arxiv-papers,paper-chunks")
        stats = await self.get(index, "/arxiv-papers,paper-chunks/_stats?level=shards")
        segments = await self.get(index, "/arxiv-papers,paper-chunks/_segments")
        if stats["_shards"]["failed"] or segments["_shards"]["failed"] or not metadata:
            raise ValueError("Incomplete index identity")
        aliases = {alias for value in metadata.values() for alias in value["aliases"]}
        if not {"arxiv-papers", "paper-chunks"} <= aliases:
            raise ValueError("Missing read alias")
        revisions = {}
        for name in metadata:
            shard_stats = stats["indices"][name]["shards"]
            primary = {shard: [entry["seq_no"] for entry in entries if entry["routing"]["primary"]]
                       for shard, entries in shard_stats.items()}
            if not primary or any(len(entries) != 1 for entries in primary.values()):
                raise ValueError("Missing primary revision")
            visible = {shard: [entry["segments"] for entry in entries if entry["routing"]["primary"]]
                       for shard, entries in segments["indices"][name]["shards"].items()}
            # Segment memory/search counters are volatile. Only identity and visibility matter.
            visible = {shard: [{seg: {k: value[k] for k in ["generation", "num_docs", "deleted_docs", "search"]}
                               for seg, value in segment.items()} for segment in entries]
                       for shard, entries in visible.items()}
            revisions[name] = {"metadata": metadata[name], "sequence": primary, "visible": visible}
        tags = await self.get(self.settings.ollama_host, "/api/tags")
        installed = {normalize_model_name(item.get("model") or item["name"]): item["digest"] for item in tags["models"]}
        required = {normalize_model_name(name) for name in [self.settings.ollama_default_model,
                    self.settings.ollama_embedding_model, *self.settings.ollama_models]}
        models = {name: installed[name] for name in sorted(required)}
        if not all(models.values()):
            raise ValueError("Missing model digest")
        corpus = await anyio.to_thread.run_sync(self.corpus, abandon_on_cancel=True)
        return {"corpus": corpus, "indexes": hashlib.sha256(canonical(revisions).encode()).hexdigest(), "models": models}

    async def close(self):
        await self.http.aclose()


def make_answer_cache(settings):
    if not settings.answer_cache_enabled:
        return None
    from redis.asyncio import Redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    redis = Redis.from_url(settings.answer_cache_url.get_secret_value(), socket_timeout=0.25,
                           socket_connect_timeout=0.25, retry=Retry(NoBackoff(), 0), max_connections=4)
    return AnswerCache(redis, ResourceIdentity(settings), settings)
