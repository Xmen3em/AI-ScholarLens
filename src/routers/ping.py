import logging

import anyio
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from src.dependencies import DatabaseDep, OllamaDep, SearchDep, SettingsDep
from src.operations import emit_event
from src.schemas.api.health import HealthResponse, ServiceStatus

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/ping", tags=["Health"])
async def ping():
    return {"status": "ok", "message": "pong"}


@router.get("/health", response_model=HealthResponse, tags=["Health"], summary="Dependency readiness")
async def health_check(
    response: Response,
    settings: SettingsDep,
    database: DatabaseDep,
    ollama: OllamaDep,
    search: SearchDep,
) -> HealthResponse:
    services: dict[str, ServiceStatus] = {}
    overall_status = "healthy"

    def check_database():
        with database.get_session() as session:
            session.execute(text("SELECT 1"))

    try:
        with anyio.fail_after(2):
            await anyio.to_thread.run_sync(check_database, abandon_on_cancel=True)
        services["database"] = ServiceStatus(status="healthy", message="Connected successfully")
    except Exception:
        emit_event("readiness_failed", level=logging.ERROR, dependency="database")
        services["database"] = ServiceStatus(status="unhealthy", message="Database is unavailable")
        overall_status = "unhealthy"

    try:
        with anyio.fail_after(2):
            readiness = await ollama.readiness()
        missing = [*readiness.missing_required, *readiness.missing_optional]
        message = (
            "All configured Ollama models are available"
            if not missing
            else f"Missing Ollama models: {', '.join(missing)}"
        )
        services["ollama"] = ServiceStatus(status=readiness.status, message=message)
        if readiness.status == "unhealthy":
            overall_status = "unhealthy"
        elif readiness.status == "degraded" and overall_status == "healthy":
            overall_status = "degraded"
    except Exception:
        emit_event("readiness_failed", level=logging.ERROR, dependency="ollama")
        services["ollama"] = ServiceStatus(status="unhealthy", message="Ollama is unavailable")
        overall_status = "unhealthy"

    def check_search():
        client = search.client
        cluster = client.cluster.health(request_timeout=2, params={"timeout": "2s"})
        if cluster.get("status") not in {"green", "yellow"} or cluster.get("timed_out", False):
            raise ValueError("Search cluster is not ready")
        for alias in ("arxiv-papers", "paper-chunks"):
            if not client.indices.exists_alias(name=alias, request_timeout=2):
                raise ValueError("Search read alias is missing")

    try:
        with anyio.fail_after(2):
            await anyio.to_thread.run_sync(check_search, abandon_on_cancel=True)
        services["opensearch"] = ServiceStatus(status="healthy", message="Cluster and read aliases are available")
    except Exception:
        emit_event("readiness_failed", level=logging.ERROR, dependency="opensearch")
        services["opensearch"] = ServiceStatus(status="unhealthy", message="Search is unavailable or read aliases are missing")
        overall_status = "unhealthy"

    if overall_status == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        service_name=settings.service_name,
        services=services,
    )
