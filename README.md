# Cloud-native Operational Assistant on AWS

> **Agent-assisted operational service deployed on Kubernetes with CI/CD, observability and secure internal integrations**

Operational assistant for support workflows deployed as a cloud-native service on Kubernetes.  
The system accepts structured incident requests via API, routes them through an orchestration layer to the appropriate tool adapter, stores results with full audit trail, and exposes operational metrics — all running on AWS EKS with automated deployments via GitHub Actions.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS EKS Cluster                         │
│  namespace: operational-assistant                               │
│                                                                  │
│  ┌──────────────┐    ┌─────────────────────────────────────┐   │
│  │   Ingress    │───▶│           FastAPI App               │   │
│  │  (AWS ALB)   │    │                                     │   │
│  └──────────────┘    │  ┌─────────┐  ┌────────────────┐   │   │
│                       │  │   API   │  │ Orchestration  │   │   │
│                       │  │ Routes  │─▶│    Layer       │   │   │
│                       │  └─────────┘  │ Plan→Exec→Sum  │   │   │
│                       │               └───────┬────────┘   │   │
│                       │                       │            │   │
│                       │         ┌─────────────▼──────────┐ │   │
│                       │         │     Adapter Layer       │ │   │
│                       │         │  ┌──────────────────┐   │ │   │
│                       │         │  │  log_adapter     │   │ │   │
│                       │         │  │  status_adapter  │   │ │   │
│                       │         │  │  deploy_adapter  │   │ │   │
│                       │         │  └──────────────────┘   │ │   │
│                       │         └────────────────────────┘ │   │
│                       │                                     │   │
│                       │  ┌──────────┐  ┌────────────────┐  │   │
│                       │  │  SQLite  │  │  Audit + Logs  │  │   │
│                       │  │ Storage  │  │  (JSON stdout) │  │   │
│                       │  └──────────┘  └────────────────┘  │   │
│                       └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
   AWS ECR (image registry)      GitHub Actions (CI/CD)
```

### Layer breakdown

| Layer | Responsibility |
|---|---|
| **API** | FastAPI routes, input validation, HTTP middleware |
| **Orchestration** | Planner → Executor → Summarizer pattern |
| **Adapters** | Isolated tool integrations (log, status, deployment) |
| **Storage** | SQLite request store + audit log table |
| **Observability** | Structured JSON logs, in-memory metrics, `/metrics` endpoint |

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.12, FastAPI |
| Container | Docker (multi-stage, non-root) |
| Orchestration | Kubernetes on AWS EKS |
| Image Registry | AWS ECR |
| CI/CD | GitHub Actions |
| Storage | SQLite (MVP), DynamoDB-ready |
| Logging | python-json-logger → stdout → CloudWatch |
| Security | RBAC, NetworkPolicy, IRSA, non-root container |

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/version` | Build version + commit |
| `POST` | `/request` | Create operational request |
| `GET` | `/requests/{id}` | Fetch request result |
| `GET` | `/metrics` | Runtime statistics |

### POST /request — example

```bash
curl -X POST http://localhost:8080/request \
  -H "Content-Type: application/json" \
  -d '{
    "request_type": "check_service_status",
    "target_service": "payment-service",
    "environment": "production",
    "parameters": {}
  }'
```

**Supported `request_type` values:**

| Value | Adapter used | Description |
|---|---|---|
| `check_service_status` | service_status_adapter | Health, replicas, resource usage |
| `get_logs` | log_adapter | Recent log entries with optional level filter |
| `get_deployment_info` | deployment_info_adapter | Image, commit, pipeline metadata |
| `simulate_restart` | service_status_adapter | Pre/post restart simulation |
| `summarize_incident` | log_adapter | Rule-based incident severity + recommendation |

---

## Deployment Flow

```
git push origin main
        │
        ▼
  GitHub Actions
        │
        ├── 1. Lint (ruff) + Unit tests (pytest)
        │
        ├── 2. Build Docker image
        │       └─ tag: <short-git-sha>
        │
        ├── 3. Trivy image vulnerability scan (blocks on CRITICAL)
        │
        ├── 4. Push image to AWS ECR
        │
        └── 5. Deploy to EKS  [requires "production" environment approval]
                ├─ kubectl apply namespace, RBAC, ConfigMap
                ├─ Inject secrets from GitHub Secrets → K8s Secret
                ├─ kubectl set image (rolling update)
                └─ kubectl rollout status (waits 120s)
```

---

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
uvicorn app.main:app --reload --port 8080

# Run tests
pytest tests/ -v
```

---

## Security Considerations

| Concern | Mitigation |
|---|---|
| **Secrets in repo** | None committed. Injected at deploy-time from GitHub Secrets via `kubectl apply` pipeline step |
| **Container privileges** | Non-root user (UID 1001), `readOnlyRootFilesystem`, all Linux capabilities dropped |
| **K8s RBAC** | Dedicated ServiceAccount with minimal Role (read ConfigMaps/Pods only) |
| **Input validation** | Pydantic models with regex validation on `target_service`, enum constraints on `request_type` and `environment` |
| **Network isolation** | NetworkPolicy allows ingress only from `kube-system` namespace, egress only DNS + HTTPS |
| **IAM** | IRSA (IAM Roles for Service Accounts) — no static credentials in pods |
| **Image scanning** | Trivy runs in CI pipeline, blocks on CRITICAL CVEs |

---

## Observability

### Structured logs (JSON)

Every request emits structured JSON to stdout:

```json
{
  "asctime": "2024-01-15T10:23:45",
  "name": "app.api.routes",
  "levelname": "INFO",
  "message": "event=request_received",
  "request_id": "3f7a1b2c-...",
  "request_type": "check_service_status",
  "target_service": "payment-service",
  "environment": "production"
}
```

### Log forwarding (concept)

In production, stdout logs flow to **CloudWatch Logs** via the EKS Fluent Bit DaemonSet:

```
Pod stdout
  └─▶ Fluent Bit DaemonSet (per node)
        └─▶ CloudWatch Log Group: /eks/operational-assistant/app
              └─▶ CloudWatch Insights queries / alarms
```

### Metrics endpoint

`GET /metrics` returns runtime counters suitable for polling from Prometheus or a dashboard:

```json
{
  "total_requests": 42,
  "successful_requests": 40,
  "failed_requests": 2,
  "requests_by_type": {"check_service_status": 20, "get_logs": 15, ...},
  "average_duration_ms": 34.5,
  "uptime_seconds": 3600.0
}
```

**Prometheus integration path (bonus):** replace `MetricsStore` with `prometheus_client` counters and expose `/metrics` in Prometheus exposition format — zero changes to the rest of the app.

---

## Future Improvements

| Improvement | Why |
|---|---|
| **Full observability stack** | Replace in-memory metrics with Prometheus + Grafana. Add distributed tracing (OpenTelemetry → Jaeger/X-Ray) |
| **Production RBAC hardening** | Add OPA/Gatekeeper policies. Separate read/write service accounts |
| **Event-driven processing** | Move `POST /request` to async via SQS → Lambda/consumer. Decouple API from execution |
| **Multi-agent orchestration** | Replace rule-based planner with LLM-backed router (Claude / GPT-4) for natural language incident requests |
| **DynamoDB storage** | Replace SQLite with DynamoDB for horizontal scalability and TTL-based audit log retention |
| **Helm chart** | Parameterise K8s manifests for multi-environment deployments |
| **Terraform** | IaC for EKS cluster, ECR repo, IAM roles, VPC |
| **Dependency scanning** | Add `pip-audit` to CI pipeline for CVE scanning of Python dependencies |
