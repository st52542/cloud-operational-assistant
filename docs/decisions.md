# Architectural Decisions

---

## ADR-001: FastAPI as the web framework

**Decision:** Use FastAPI (Python 3.12) for the API layer.

**Context:** The service needs to expose a small HTTP API, validate structured inputs, and serialize JSON responses. Python was chosen because the team is already building data/ML tooling in Python and wants a consistent language across services.

**Rationale:**
- Pydantic v2 models provide automatic request validation with clear error messages — critical for a service that accepts structured operational commands.
- FastAPI generates OpenAPI documentation automatically, which acts as a contract for internal consumers.
- The async-capable foundation (Starlette) makes future SQS or WebSocket integration straightforward.
- Startup time is faster than Django; significantly simpler than building raw ASGI apps.

**Alternatives considered:** Flask (no built-in validation), Django (too heavy for a single-service API), Go (faster runtime, but no shared language with the AI/data tooling).

---

## ADR-002: Adapter layer with explicit routing table

**Decision:** Isolate all tool integrations behind adapter modules with a uniform `run(target_service, environment, parameters) -> dict` interface. Route from `request_type` to adapter via a Python dict (`ADAPTER_REGISTRY`).

**Context:** The orchestrator needs to invoke different "tools" depending on the request type, without the API layer or storage layer knowing which tool was used.

**Rationale:**
- The adapter pattern decouples the orchestration logic from specific integrations. Replacing a mock adapter with a real AWS SDK call requires no changes outside `app/adapters/`.
- The routing table is a simple, inspectable Python dict — no framework, no magic. This mirrors how production agent systems work, where a "tool registry" maps capability names to function pointers.
- Each adapter is independently testable in isolation.

**Trade-offs:** The routing table requires updating when new request types are added. This is intentional — it makes the set of supported operations explicit and auditable.

---

## ADR-003: SQLite for MVP storage

**Decision:** Use SQLite with a file at `/data/operational_assistant.db` as the persistence backend.

**Context:** The service needs to store request state and an append-only audit log. For a portfolio/MVP deployment, operational simplicity matters more than scalability.

**Rationale:**
- Zero external dependencies — no RDS, no DynamoDB, no Redis to provision or pay for during demo periods.
- SQLite supports concurrent reads and serialized writes, which is sufficient for a single-pod demo service.
- The storage layer (`app/storage/database.py`) uses plain functions with no ORM. Swapping to DynamoDB requires replacing those functions only — the rest of the application is unaffected.
- The two-table schema (requests + audit_log) maps cleanly to a future DynamoDB design: `operational_requests` as a primary table keyed by `request_id`, `audit_log` as a time-series table with a GSI on `request_id`.

**Trade-offs:** SQLite does not support multi-pod writes. For a multi-replica production deployment, this must be replaced with DynamoDB or Aurora Serverless. The Kubernetes `emptyDir` volume means data is lost on pod restart — acceptable for MVP, not for production.

**Migration path:** Replace `app/storage/database.py` functions with `boto3` DynamoDB calls. No other files change.

---

## ADR-004: EKS over k3s / standalone EC2

**Decision:** Deploy on Amazon EKS rather than k3s on EC2 or any self-managed Kubernetes distribution.

**Context:** The project must demonstrate cloud-native Kubernetes operations as part of its purpose. The deployment target is AWS.

**Rationale:**
- EKS is the de-facto standard for Kubernetes on AWS. Recruiters and hiring managers recognise it immediately.
- IRSA (IAM Roles for Service Accounts) is only available on EKS and provides the most secure way to grant pods access to AWS APIs without static credentials.
- The AWS Load Balancer Controller (used for the ALB Ingress) integrates natively with EKS.
- EKS managed node groups handle node lifecycle, AMI patching, and Kubernetes version upgrades.

**Trade-offs:** EKS has a non-trivial cost (~$0.10/hour for control plane + EC2 nodes). For short-lived portfolio demos, the cluster can be created and destroyed with Terraform. k3s on a single EC2 t3.small would be cheaper but would not demonstrate EKS-specific capabilities (IRSA, ALB controller, managed node groups).

---

## ADR-005: Structured JSON logs over plain text

**Decision:** All application log output is JSON, emitted to stdout, using `python-json-logger`.

**Context:** The service runs in Kubernetes. Log aggregation is handled externally (Fluent Bit → CloudWatch). The logging format must be machine-parseable.

**Rationale:**
- JSON logs can be queried directly with CloudWatch Logs Insights using field syntax (`fields @timestamp, request_id, duration_ms`).
- Every log line includes a `request_id` field, enabling distributed trace reconstruction without a dedicated tracing backend — useful at MVP scale.
- `python-json-logger` integrates with Python's standard `logging` module. Switching log levels, adding handlers, or redirecting output requires no application code changes.
- JSON is self-describing: adding a new field to a log line (e.g. `adapter_name`) does not require a schema migration.

**Alternatives considered:** Plain text + regex parsing (fragile), OpenTelemetry SDK (correct long-term direction, but over-engineered for MVP), structlog (good library, adds a dependency and a non-standard API).

**Future:** Add trace context propagation (W3C `traceparent` header) to correlate logs across service calls. Replace in-memory `MetricsStore` with OpenTelemetry metrics SDK for vendor-agnostic export to Prometheus, Datadog, or CloudWatch.

---

## ADR-006: Planner → Executor → Summarizer as orchestration pattern

**Decision:** Structure the orchestration layer as a three-phase pipeline (Plan, Execute, Summarize) rather than a flat function.

**Context:** The project spec asks for an architecture that "looks like something that could be used in a real environment" and shows understanding of agent-oriented design.

**Rationale:**
- The three-phase separation makes the system's decision-making inspectable: the `plan` object returned in every response shows which adapter was selected and why.
- The Planner is the natural injection point for an LLM router: replace the `ADAPTER_REGISTRY` dict lookup with an LLM call that classifies the request and selects a tool.
- The Executor handles the imperative logic (calling the adapter, managing errors, handling special flows like restart simulation).
- The Summarizer produces a consistent response envelope regardless of which adapter was used — consumers always see the same `plan`/`data`/`meta` structure.

**Trade-offs:** Three phases add indirection over a simple `if request_type == ...` block. For three adapters, this is overengineering in isolation — but it is the correct foundation for a system that will grow to handle more request types and eventually LLM-driven routing.
