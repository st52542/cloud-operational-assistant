# Architecture

## Overview

The system is a synchronous request-processing service structured in five distinct layers. Each layer has a single responsibility. The boundary between layers is explicit — upper layers call into lower ones; lower layers never import from upper ones.

```
HTTP Client
    │
    ▼
┌──────────────────┐
│   API Layer      │  FastAPI routes, input validation, HTTP middleware
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Orchestration    │  Planner → Executor → Summarizer
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Adapter Layer   │  log_adapter / service_status_adapter / deployment_info_adapter
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Storage Layer   │  SQLite: operational_requests + audit_log tables
└──────────────────┘
         │ (all layers write to)
         ▼
┌──────────────────┐
│ Observability    │  Structured JSON logs + in-memory MetricsStore
└──────────────────┘
```

---

## Layer Details

### 1. API Layer (`app/api/routes.py`)

Handles the HTTP surface of the application. Responsibilities:
- Parse and validate incoming JSON via Pydantic models
- Generate `request_id` (UUID4)
- Delegate to the Orchestration layer
- Serialize response back to JSON
- Handle HTTP-level errors (404 for missing request IDs)

The API layer does **not** contain business logic. It is a thin adapter between HTTP and the orchestration service.

### 2. Orchestration Layer (`app/services/orchestrator.py`)

Implements the **Planner → Executor → Summarizer** agent pattern:

**Planner:** Given a `request_type`, resolves the correct adapter from the `ADAPTER_REGISTRY` routing table and assigns a named strategy (e.g. `query_and_report`, `fetch_logs_then_summarize`). This is where future LLM-based routing would be plugged in.

**Executor:** Calls the adapter's `run()` function. Handles special cases like restart simulation (pre/post state capture) and incident summarization (rule-based severity classification).

**Summarizer:** Wraps raw adapter output into a unified response envelope:
```json
{
  "plan": { "request_type": "...", "adapter_used": "...", "strategy": "..." },
  "data": { ... },
  "meta": { "execution_duration_ms": 12.4, "source": "simulated" }
}
```

### 3. Adapter Layer (`app/adapters/`)

Each adapter is an isolated module with a single `run(target_service, environment, parameters) -> dict` function. Adapters simulate internal infrastructure integrations:

| Adapter | Simulates |
|---|---|
| `log_adapter` | Log aggregation system (e.g. CloudWatch, Loki) |
| `service_status_adapter` | Internal health-check registry or Kubernetes metrics |
| `deployment_info_adapter` | CI/CD system deployment metadata API |

Adapters return mock/simulated data. In production, each adapter would be replaced with a real HTTP client or AWS SDK call, with no changes needed to the orchestration or API layers.

### 4. Storage Layer (`app/storage/database.py`)

Two SQLite tables:

**`operational_requests`** — one row per API request:
```
request_id | request_type | target_service | environment | status | result (JSON) | error | duration_ms | created_at | updated_at
```

**`audit_log`** — append-only event stream:
```
id | request_id | event | details (JSON) | timestamp
```

Events written per request lifecycle: `request_created` → `processing_started` → `request_completed` / `request_failed`.

### 5. Observability Layer (`app/observability/`)

**Logger (`logger.py`):** All application code calls `get_logger(__name__)`. This returns a Python logger configured with `python-json-logger`, which emits every log line as a JSON object to stdout. In Kubernetes, stdout is captured by the Fluent Bit DaemonSet and forwarded to CloudWatch Logs.

**MetricsStore (`metrics.py`):** An in-memory singleton that counts requests, tracks durations, and records HTTP traffic. Exposed via `GET /metrics`. In production, this would be replaced with `prometheus_client` metrics, with a `/metrics` endpoint in Prometheus exposition format scraped by a Prometheus server.

---

## Data Flow: POST /request

```
1. Client sends POST /request
2. HTTP middleware assigns request_id, logs request_start
3. Pydantic validates body (request_type enum, target_service regex, environment enum)
4. Route handler calls storage.create_request() → status=pending
5. Route calls orchestrator.process_request()
   5a. Planner: resolves adapter from registry
   5b. Executor: calls adapter.run(), handles special flows
   5c. Summarizer: wraps result in unified envelope
6. Route handler calls storage.update_request() → status=completed + result
7. Audit log: request_created, processing_started, request_completed
8. MetricsStore.record_operational_request()
9. Response returned to client
```

---

## Kubernetes Topology

```
                         Internet / VPN
                               │
                    ┌──────────▼──────────┐
                    │   AWS ALB Ingress   │
                    └──────────┬──────────┘
                               │ HTTPS
                    ┌──────────▼──────────┐
                    │  K8s Service (CIP)  │
                    └──────┬──────┬───────┘
                           │      │
              ┌────────────▼┐    ┌▼────────────┐
              │   Pod (AZ-a)│    │  Pod (AZ-b) │   RollingUpdate
              │  replica 1  │    │  replica 2  │   maxUnavailable=1
              └─────────────┘    └─────────────┘
                    │ emptyDir /data (MVP)
                    │ → replace with EFS PVC for production
```

---

## Extension Points

| Where to extend | What to add |
|---|---|
| `ADAPTER_REGISTRY` in orchestrator | New request_type → adapter mappings |
| `app/adapters/` | New adapter modules (real HTTP clients, AWS SDK) |
| `app/services/orchestrator.py` planner | LLM-based routing for natural language requests |
| `app/storage/database.py` | Swap SQLite functions for DynamoDB boto3 calls |
| `app/observability/metrics.py` | Replace MetricsStore with `prometheus_client` |
