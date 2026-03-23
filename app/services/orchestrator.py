"""
Orchestration layer: Planner -> Executor -> Summarizer

The planner decides which adapter to call based on request_type.
The executor invokes the adapter and handles errors.
The summarizer wraps the result into a unified response format.
"""
import time
from typing import Any

from app.adapters import deployment_info_adapter, log_adapter, service_status_adapter
from app.models.schemas import RequestType
from app.observability.logger import get_logger

logger = get_logger(__name__)

# Routing table: request_type -> adapter module
ADAPTER_REGISTRY: dict[str, Any] = {
    RequestType.CHECK_SERVICE_STATUS: service_status_adapter,
    RequestType.GET_LOGS: log_adapter,
    RequestType.GET_DEPLOYMENT_INFO: deployment_info_adapter,
    RequestType.SIMULATE_RESTART: service_status_adapter,  # reuses status adapter post-restart
    RequestType.SUMMARIZE_INCIDENT: log_adapter,  # reuses log adapter for incident context
}


# ── Planner ──────────────────────────────────────────────────────────────────

def plan(request_type: str, target_service: str, environment: str) -> dict:
    """Decide which adapter and strategy to use for the given request."""
    adapter = ADAPTER_REGISTRY.get(request_type)
    if adapter is None:
        raise ValueError(f"No adapter registered for request_type='{request_type}'")

    plan_result = {
        "request_type": request_type,
        "adapter": adapter.__name__.split(".")[-1],
        "target_service": target_service,
        "environment": environment,
        "strategy": _get_strategy(request_type),
    }

    logger.info(
        "event=planner_decision",
        extra=plan_result,
    )
    return plan_result


def _get_strategy(request_type: str) -> str:
    strategies = {
        RequestType.CHECK_SERVICE_STATUS: "query_and_report",
        RequestType.GET_LOGS: "fetch_and_filter",
        RequestType.GET_DEPLOYMENT_INFO: "query_and_report",
        RequestType.SIMULATE_RESTART: "simulate_action_then_verify",
        RequestType.SUMMARIZE_INCIDENT: "fetch_logs_then_summarize",
    }
    return strategies.get(request_type, "default")


# ── Executor ─────────────────────────────────────────────────────────────────

def execute(plan_result: dict, parameters: dict) -> dict:
    """Call the resolved adapter and return raw result."""
    adapter = ADAPTER_REGISTRY[plan_result["request_type"]]
    target_service = plan_result["target_service"]
    environment = plan_result["environment"]
    request_type = plan_result["request_type"]

    start = time.perf_counter()

    if request_type == RequestType.SIMULATE_RESTART:
        raw = _simulate_restart(adapter, target_service, environment, parameters)
    elif request_type == RequestType.SUMMARIZE_INCIDENT:
        raw = _summarize_incident(adapter, target_service, environment, parameters)
    else:
        raw = adapter.run(target_service, environment, parameters)

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    raw["execution_duration_ms"] = duration_ms

    logger.info(
        "event=executor_completed",
        extra={
            "adapter": plan_result["adapter"],
            "target_service": target_service,
            "environment": environment,
            "duration_ms": duration_ms,
        },
    )
    return raw


def _simulate_restart(adapter, target_service: str, environment: str, parameters: dict) -> dict:
    """Simulate a restart by checking pre-state, describing action, then post-state."""
    pre_state = adapter.run(target_service, environment, parameters)
    post_state = adapter.run(target_service, environment, parameters)
    post_state["status"] = "healthy"
    post_state["replicas"]["ready"] = post_state["replicas"]["total"]

    return {
        "adapter": "restart_simulation",
        "service": target_service,
        "environment": environment,
        "action": "simulate_restart",
        "pre_restart_state": pre_state,
        "restart_initiated": True,
        "post_restart_state": post_state,
        "note": "This is a simulated restart. No actual pod was affected.",
        "source": "simulated",
    }


def _summarize_incident(adapter, target_service: str, environment: str, parameters: dict) -> dict:
    """Fetch recent logs and produce a rule-based incident summary."""
    log_data = adapter.run(target_service, environment, {**parameters, "limit": 30})
    logs = log_data.get("logs", [])

    error_count = sum(1 for l in logs if l["level"] == "ERROR")
    warn_count = sum(1 for l in logs if l["level"] == "WARN")
    info_count = sum(1 for l in logs if l["level"] == "INFO")

    severity = "low"
    if error_count >= 5:
        severity = "high"
    elif error_count >= 2 or warn_count >= 5:
        severity = "medium"

    unique_errors = list({l["message"] for l in logs if l["level"] == "ERROR"})

    return {
        "adapter": "incident_summarizer",
        "service": target_service,
        "environment": environment,
        "incident_summary": {
            "severity": severity,
            "log_window_count": len(logs),
            "error_count": error_count,
            "warn_count": warn_count,
            "info_count": info_count,
            "unique_error_messages": unique_errors,
            "recommendation": _recommend(severity, unique_errors),
        },
        "raw_logs_sample": logs[:5],
        "source": "rule_based_analysis",
    }


def _recommend(severity: str, errors: list) -> str:
    if severity == "high":
        return "Immediate escalation recommended. Assign to L2 engineer and open incident ticket."
    elif severity == "medium":
        return "Monitor closely. Consider rolling restart if errors persist beyond 15 minutes."
    return "No immediate action required. Continue standard monitoring."


# ── Summarizer ───────────────────────────────────────────────────────────────

def summarize(raw_result: dict, plan_result: dict) -> dict:
    """Wrap raw adapter output into a clean unified response."""
    return {
        "plan": {
            "request_type": plan_result["request_type"],
            "adapter_used": plan_result["adapter"],
            "strategy": plan_result["strategy"],
        },
        "data": raw_result,
        "meta": {
            "execution_duration_ms": raw_result.pop("execution_duration_ms", None),
            "source": raw_result.get("source", "unknown"),
        },
    }


# ── Public entry point ────────────────────────────────────────────────────────

def process_request(
    request_id: str,
    request_type: str,
    target_service: str,
    environment: str,
    parameters: dict,
) -> tuple[dict, float]:
    """Full planner -> executor -> summarizer pipeline. Returns (result, duration_ms)."""
    logger.info(
        "event=orchestration_start",
        extra={
            "request_id": request_id,
            "request_type": request_type,
            "target_service": target_service,
            "environment": environment,
        },
    )

    t0 = time.perf_counter()

    planned = plan(request_type, target_service, environment)
    raw = execute(planned, parameters)
    result = summarize(raw, planned)

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)

    logger.info(
        "event=orchestration_complete",
        extra={
            "request_id": request_id,
            "duration_ms": duration_ms,
            "status": "completed",
        },
    )

    return result, duration_ms
