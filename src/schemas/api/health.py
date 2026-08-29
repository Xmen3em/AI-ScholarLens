from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ServiceStatus(BaseModel):
    """Individual service status."""

    status: str = Field(..., description="Service status", json_schema_extra={"example": "healthy"})
    message: Optional[str] = Field(None, description="Status message", json_schema_extra={"example": "Connected successfully"})


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str = Field(..., description="Overall health status", json_schema_extra={"example": "ok"})
    version: str = Field(..., description="Application version", json_schema_extra={"example": "0.1.0"})
    environment: str = Field(..., description="Deployment environment", json_schema_extra={"example": "development"})
    service_name: str = Field(..., description="Service identifier", json_schema_extra={"example": "rag-api"})
    services: Optional[Dict[str, ServiceStatus]] = Field(None, description="Individual service statuses")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "version": "0.1.0",
                "environment": "development",
                "service_name": "rag-api",
                "services": {
                    "database": {"status": "healthy", "message": "Connected successfully"},
                    "pdf_parser": {"status": "healthy", "message": "Docling parser ready"},
                },
            }
        }
    )
