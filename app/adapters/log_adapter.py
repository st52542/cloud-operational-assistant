import random
from datetime import datetime, timedelta, timezone
from typing import Any


LOG_TEMPLATES = [
    {"level": "INFO", "message": "Request processed successfully", "latency_ms": None},
    {"level": "INFO", "message": "Health check passed", "latency_ms": None},
    {"level": "WARN", "message": "High memory usage detected", "latency_ms": None},
    {"level": "ERROR", "message": "Database connection timeout", "latency_ms": None},
    {"level": "INFO", "message": "Cache hit ratio: 94%", "latency_ms": None},
    {"level": "INFO", "message": "Autoscaler: replica count unchanged", "latency_ms": None},
    {"level": "WARN", "message": "Slow query detected", "latency_ms": None},
]


def run(target_service: str, environment: str, parameters: dict[str, Any]) -> dict[str, Any]:
    limit = int(parameters.get("limit", 20))
    level_filter = parameters.get("level", None)

    base_time = datetime.now(timezone.utc)
    logs = []

    for i in range(min(limit, 50)):
        template = random.choice(LOG_TEMPLATES)
        ts = base_time - timedelta(seconds=i * random.randint(5, 30))
        entry = {
            "timestamp": ts.isoformat(),
            "level": template["level"],
            "service": target_service,
            "environment": environment,
            "message": template["message"],
            "trace_id": f"tr-{random.randint(100000, 999999)}",
        }
        if level_filter and entry["level"] != level_filter.upper():
            continue
        logs.append(entry)

    return {
        "adapter": "log_adapter",
        "service": target_service,
        "environment": environment,
        "log_count": len(logs),
        "logs": logs,
        "source": "simulated",
    }
