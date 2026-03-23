import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    HealthResponse,
    MetricsResponse,
    OperationalRequestCreate,
    OperationalRequestResponse,
    RequestStatus,
    VersionResponse,
)
from app.observability.logger import get_logger
from app.observability.metrics import metrics_store
from app.services.orchestrator import process_request
from app.storage.database import (
    count_requests_by_env,
    count_requests_by_type,
    create_request,
    get_avg_duration,
    get_request,
    update_request,
    write_audit_log,
)

router = APIRouter()
logger = get_logger(__name__)


def _row_to_response(row: dict) -> OperationalRequestResponse:
    return OperationalRequestResponse(
        request_id=row["request_id"],
        request_type=row["request_type"],
        target_service=row["target_service"],
        environment=row["environment"],
        status=row["status"],
        result=json.loads(row["result"]) if row.get("result") else None,
        error=row.get("error"),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        duration_ms=row.get("duration_ms"),
    )


@router.get("/health", response_model=HealthResponse, tags=["ops"])
def health():
    return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc))


@router.get("/version", response_model=VersionResponse, tags=["ops"])
def version():
    return VersionResponse(
        version="1.0.0",
        service="cloud-operational-assistant",
        build_commit=os.environ.get("BUILD_COMMIT", "local"),
    )


@router.post("/request", response_model=OperationalRequestResponse, status_code=202, tags=["requests"])
def create_operational_request(body: OperationalRequestCreate):
    request_id = str(uuid.uuid4())

    logger.info(
        "event=request_received",
        extra={
            "request_id": request_id,
            "request_type": body.request_type,
            "target_service": body.target_service,
            "environment": body.environment,
        },
    )

    row = create_request(
        request_id=request_id,
        request_type=body.request_type,
        target_service=body.target_service,
        environment=body.environment,
        parameters=body.parameters or {},
    )
    write_audit_log(request_id, "request_created", {"request_type": body.request_type})

    try:
        update_request(request_id, status=RequestStatus.PROCESSING)
        write_audit_log(request_id, "processing_started")

        result, duration_ms = process_request(
            request_id=request_id,
            request_type=body.request_type,
            target_service=body.target_service,
            environment=body.environment,
            parameters=body.parameters or {},
        )

        row = update_request(
            request_id=request_id,
            status=RequestStatus.COMPLETED,
            result=result,
            duration_ms=duration_ms,
        )
        write_audit_log(
            request_id,
            "request_completed",
            {"duration_ms": duration_ms, "adapter": result.get("plan", {}).get("adapter_used")},
        )
        metrics_store.record_operational_request(
            body.request_type, body.environment, success=True, duration_ms=duration_ms
        )

    except Exception as exc:
        logger.error(
            "event=request_failed",
            extra={"request_id": request_id, "error": str(exc)},
        )
        row = update_request(request_id, status=RequestStatus.FAILED, error=str(exc))
        write_audit_log(request_id, "request_failed", {"error": str(exc)})
        metrics_store.record_operational_request(
            body.request_type, body.environment, success=False, duration_ms=0
        )

    return _row_to_response(row)


@router.get("/requests/{request_id}", response_model=OperationalRequestResponse, tags=["requests"])
def get_operational_request(request_id: str):
    row = get_request(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Request '{request_id}' not found")
    return _row_to_response(row)


@router.get("/metrics", response_model=MetricsResponse, tags=["ops"])
def get_metrics():
    return MetricsResponse(
        total_requests=metrics_store.total_requests,
        successful_requests=metrics_store.successful_requests,
        failed_requests=metrics_store.failed_requests,
        requests_by_type=metrics_store.requests_by_type or count_requests_by_type(),
        requests_by_environment=metrics_store.requests_by_environment or count_requests_by_env(),
        average_duration_ms=metrics_store.average_duration_ms or get_avg_duration(),
        http_requests_total=metrics_store.http_requests_total,
        uptime_seconds=metrics_store.uptime_seconds,
    )