from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class RequestType(str, Enum):
    CHECK_SERVICE_STATUS = "check_service_status"
    GET_LOGS = "get_logs"
    GET_DEPLOYMENT_INFO = "get_deployment_info"
    SIMULATE_RESTART = "simulate_restart"
    SUMMARIZE_INCIDENT = "summarize_incident"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class RequestStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OperationalRequestCreate(BaseModel):
    request_type: RequestType
    target_service: str = Field(..., min_length=1, max_length=128)
    environment: Environment
    parameters: Optional[dict[str, Any]] = Field(default_factory=dict)

    @field_validator("target_service")
    @classmethod
    def validate_target_service(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", v):
            raise ValueError("target_service must contain only alphanumeric characters, hyphens, underscores, and dots")
        return v.lower()


class OperationalRequestResponse(BaseModel):
    request_id: str
    request_type: RequestType
    target_service: str
    environment: Environment
    status: RequestStatus
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    duration_ms: Optional[float] = None


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class VersionResponse(BaseModel):
    version: str
    service: str
    build_commit: Optional[str] = None


class MetricsResponse(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    requests_by_type: dict[str, int]
    requests_by_environment: dict[str, int]
    average_duration_ms: float
    http_requests_total: int
    uptime_seconds: float
