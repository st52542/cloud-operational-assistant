import random
from datetime import datetime, timezone
from typing import Any

SERVICES_DB = {
    "default": {
        "statuses": ["healthy", "healthy", "healthy", "degraded", "unhealthy"],
        "replicas": 3,
        "cpu_threshold": 80,
        "mem_threshold": 75,
    }
}


def run(target_service: str, environment: str, parameters: dict[str, Any]) -> dict[str, Any]:
    config = SERVICES_DB.get(target_service, SERVICES_DB["default"])

    status = random.choices(
        config["statuses"],
        weights=[60, 60, 60, 15, 5],
        k=1,
    )[0]

    replicas_total = config["replicas"]
    replicas_ready = replicas_total if status == "healthy" else random.randint(1, replicas_total - 1)

    cpu_usage = round(random.uniform(10, config["cpu_threshold"] + 10), 1)
    mem_usage = round(random.uniform(20, config["mem_threshold"] + 10), 1)

    checks = {
        "http_health": status != "unhealthy",
        "database_connection": random.random() > 0.05,
        "cache_connection": random.random() > 0.02,
        "downstream_dependencies": status == "healthy",
    }

    return {
        "adapter": "service_status_adapter",
        "service": target_service,
        "environment": environment,
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "replicas": {
            "total": replicas_total,
            "ready": replicas_ready,
            "available": replicas_ready,
        },
        "resources": {
            "cpu_usage_percent": cpu_usage,
            "memory_usage_percent": mem_usage,
        },
        "health_checks": checks,
        "source": "simulated",
    }
