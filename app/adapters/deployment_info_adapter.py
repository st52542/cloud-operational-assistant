import random
import string
from datetime import datetime, timedelta, timezone
from typing import Any


def _random_sha() -> str:
    return "".join(random.choices(string.hexdigits[:16], k=7))


def run(target_service: str, environment: str, parameters: dict[str, Any]) -> dict[str, Any]:
    deployed_days_ago = random.randint(0, 14)
    deploy_time = datetime.now(timezone.utc) - timedelta(days=deployed_days_ago, hours=random.randint(0, 23))

    image_tag = f"v1.{random.randint(0, 9)}.{random.randint(0, 20)}"
    commit_sha = _random_sha()

    env_configs = {
        "production": {"namespace": "prod", "replicas": 3, "hpa": True},
        "staging": {"namespace": "staging", "replicas": 2, "hpa": False},
        "development": {"namespace": "dev", "replicas": 1, "hpa": False},
    }
    env_cfg = env_configs.get(environment, env_configs["development"])

    return {
        "adapter": "deployment_info_adapter",
        "service": target_service,
        "environment": environment,
        "deployment": {
            "name": f"{target_service}-deployment",
            "namespace": env_cfg["namespace"],
            "image": f"123456789.dkr.ecr.eu-west-1.amazonaws.com/{target_service}:{image_tag}",
            "image_tag": image_tag,
            "commit_sha": commit_sha,
            "replicas_desired": env_cfg["replicas"],
            "replicas_ready": env_cfg["replicas"],
            "strategy": "RollingUpdate",
            "deployed_at": deploy_time.isoformat(),
            "deployed_days_ago": deployed_days_ago,
        },
        "k8s_metadata": {
            "cluster": "operational-assistant-eks",
            "namespace": env_cfg["namespace"],
            "hpa_enabled": env_cfg["hpa"],
            "ingress": f"{target_service}.{environment}.internal.example.com",
        },
        "pipeline": {
            "triggered_by": random.choice(["push", "manual", "schedule"]),
            "pipeline_id": f"gh-run-{random.randint(1000000, 9999999)}",
            "branch": "main" if environment == "production" else "develop",
        },
        "source": "simulated",
    }
