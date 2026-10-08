import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from src.dependencies import DatabaseDep, OllamaDep, SettingsDep
from src.exceptions import OllamaException
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
) -> HealthResponse:
    services: dict[str, ServiceStatus] = {}
    overall_status = "healthy"

    try:
        with database.get_session() as session:
            session.execute(text("SELECT 1"))
        services["database"] = ServiceStatus(status="healthy", message="Connected successfully")
    except Exception:
        logger.exception("Database readiness check failed")
        services["database"] = ServiceStatus(status="unhealthy", message="Database is unavailable")
        overall_status = "unhealthy"

    try:
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
    except OllamaException:
        logger.exception("Ollama readiness check failed")
        services["ollama"] = ServiceStatus(status="unhealthy", message="Ollama is unavailable")
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
