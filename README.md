# Cloud-native Operational Assistant on AWS

> **Agent-assisted operational service deployed on Kubernetes with CI/CD, observability and secure internal integrations**

Cloud-native operational assistant for support workflows, designed to demonstrate patterns used in platform engineering, internal tooling and AIOps-style automation.
The system accepts structured incident requests via API, routes them through an orchestration layer to the appropriate tool adapter, stores results with full audit trail, and exposes operational metrics — all running on AWS EKS with automated deployments via GitHub Actions.

---

## What this project demonstrates

This project demonstrates practical design of a cloud-native operational service with:

- Kubernetes-based deployment on AWS
- CI/CD automation with GitHub Actions
- modular orchestration and adapter-based integration
- structured observability and audit logging
- security-focused runtime configuration
- architecture patterns relevant to internal support automation and AIOps-style workflows

## Real-world relevance

The design reflects patterns commonly used in internal platform tooling, support automation and operational systems where requests must be validated, routed to the correct integration layer, executed safely and recorded with a full audit trail.

---

## Quick Start

### Prerequisites

Install the following tools:

```bash
# Mac
brew install awscli eksctl kubectl
brew install --cask docker

# Windows (PowerShell as admin)
winget install Amazon.AWSCLI
choco install eksctl kubernetes-cli

# Linux
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install
curl --silent --location "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin
curl -LO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install kubectl /usr/local/bin/
```

Verify:
```bash
aws --version && eksctl version && kubectl version --client && docker --version
```

### 1. Configure AWS credentials

Create an AWS account at [aws.amazon.com](https://aws.amazon.com) (new customers receive $100 in credits).

Then create an IAM user:
1. Go to **IAM → Users → Create user**
2. Name: anything, e.g. `deploy-user`
3. Permissions: `AdministratorAccess`
4. Create **Access key** (type: CLI) and download the CSV

Configure the CLI:
```bash
aws configure
# AWS Access Key ID:     <from CSV>
# AWS Secret Access Key: <from CSV>
# Default region:        eu-west-2
# Default output format: json
```

Verify:
```bash
aws sts get-caller-identity
```

### 2. Deploy — one command

```bash
chmod +x deploy/scripts/bootstrap.sh
./deploy/scripts/bootstrap.sh
```

This will automatically:
- Create an ECR repository
- Build and push the Docker image (linux/amd64)
- Create an EKS cluster (~15 minutes)
- Deploy the application to Kubernetes

When complete you will see:
```
✅ ECR repository created
✅ Docker image pushed
✅ EKS cluster ready
✅ Application deployed

Test the app:
  kubectl port-forward -n operational-assistant svc/operational-assistant-svc 8080:80
  curl http://localhost:8080/health
```

### 3. Test the API

```bash
# Start port-forward
kubectl port-forward -n operational-assistant svc/operational-assistant-svc 8080:80
```

In a second terminal:

```bash
# Health check
curl http://localhost:8080/health

# Version
curl http://localhost:8080/version

# Create an operational request
curl -X POST http://localhost:8080/request \
  -H "Content-Type: application/json" \
  -d '{
    "request_type": "check_service_status",
    "target_service": "payment-service",
    "environment": "production"
  }'

# Other request types
curl -X POST http://localhost:8080/request \
  -H "Content-Type: application/json" \
  -d '{"request_type": "get_logs", "target_service": "auth-service", "environment": "staging", "parameters": {"limit": 10}}'

curl -X POST http://localhost:8080/request \
  -H "Content-Type: application/json" \
  -d '{"request_type": "get_deployment_info", "target_service": "api-gateway", "environment": "production"}'

curl -X POST http://localhost:8080/request \
  -H "Content-Type: application/json" \
  -d '{"request_type": "simulate_restart", "target_service": "worker-service", "environment": "staging"}'

curl -X POST http://localhost:8080/request \
  -H "Content-Type: application/json" \
  -d '{"request_type": "summarize_incident", "target_service": "payment-service", "environment": "production"}'

# Get result by ID
curl http://localhost:8080/requests/<request_id>

# Runtime metrics
curl http://localhost:8080/metrics
```

### 4. Cleanup

When you are done, delete all AWS resources to stop billing:

```bash
chmod +x deploy/scripts/destroy.sh
./deploy/scripts/destroy.sh
```

> ⚠️ This permanently deletes the EKS cluster and ECR repository including all images.

---

## CI/CD — GitHub Actions

Every `git push` to `main` automatically:
1. Runs lint (ruff) and unit tests (pytest)
2. Builds a Docker image tagged with the commit SHA
3. Pushes to ECR
4. Deploys to EKS via rolling update

### Setup

In your GitHub repository go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | from IAM CSV |
| `AWS_SECRET_ACCESS_KEY` | from IAM CSV |
| `APP_API_KEY` | any string, e.g. `demo-key-123` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS EKS Cluster                         │
│  namespace: operational-assistant                               │
│                                                                 │
│  ┌──────────────┐    ┌─────────────────────────────────────┐    │
│  │   Ingress    │───▶│           FastAPI App               │    │
│  │  (AWS ALB)   │    │                                     │    │
│  └──────────────┘    │  ┌─────────┐  ┌────────────────┐    │    │
│                      │  │   API   │  │ Orchestration  │    │    │
│                      │  │ Routes  │─▶│    Layer       │    │    │
│                      │  └─────────┘  │ Plan→Exec→Sum  │    │    │
│                      │               └───────┬────────┘    │    │
│                      │                       │             │    │
│                      │         ┌─────────────▼──────────┐  │    │
│                      │         │     Adapter Layer      │  │    │
│                      │         │  ┌──────────────────┐  │  │    │
│                      │         │  │  log_adapter     │  │  │    │
│                      │         │  │  status_adapter  │  │  │    │
│                      │         │  │  deploy_adapter  │  │  │    │
│                      │         │  └──────────────────┘  │  │    │
│                      │         └────────────────────────┘  │    │
│                      │                                     │    │
│                      │  ┌──────────┐  ┌────────────────┐   │    │
│                      │  │  SQLite  │  │  Audit + Logs  │   │    │
│                      │  │ Storage  │  │  (JSON stdout) │   │    │
│                      │  └──────────┘  └────────────────┘   │    │
│                      └─────────────────────────────────────┘    │
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
| Container | Docker (multi-stage, non-root, linux/amd64) |
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

**Supported `request_type` values:**

| Value | Adapter | Description |
|---|---|---|
| `check_service_status` | service_status_adapter | Health, replicas, resource usage |
| `get_logs` | log_adapter | Recent log entries with optional level filter |
| `get_deployment_info` | deployment_info_adapter | Image, commit, pipeline metadata |
| `simulate_restart` | service_status_adapter | Pre/post restart simulation |
| `summarize_incident` | log_adapter | Rule-based incident severity + recommendation |

---

## Running Locally (without AWS)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
uvicorn app.main:app --reload --port 8080

# Run tests
pytest tests/ -v
```

---

## Estimated AWS Cost

| Scenario | Cost |
|---|---|
| Cluster running for 3 hours (demo) | ~$0.60 |
| Cluster running for a full day | ~$5.00 |
| ECR storage (~200MB image) | ~$0.02/month |
| New AWS customers | $100 credits on sign-up |

> Always run `./deploy/scripts/destroy.sh` after your demo to stop billing.

---

## Security Considerations

| Concern | Mitigation |
|---|---|
| **Secrets in repo** | None committed. Injected at deploy-time from GitHub Secrets |
| **Container privileges** | Non-root user (UID 1001), `readOnlyRootFilesystem`, all Linux capabilities dropped |
| **K8s RBAC** | Dedicated ServiceAccount with minimal Role (read ConfigMaps/Pods only) |
| **Input validation** | Pydantic models with regex on `target_service`, enum constraints on `request_type` and `environment` |
| **Network isolation** | NetworkPolicy allows ingress only from `kube-system`, egress only DNS + HTTPS |
| **IAM** | IRSA (IAM Roles for Service Accounts) — no static credentials in pods |
| **Image scanning** | Trivy runs in CI pipeline, blocks on CRITICAL CVEs |

---

## Observability

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

View live logs from the cluster:
```bash
kubectl logs -n operational-assistant -l app=operational-assistant -f
```

In production, stdout logs flow to CloudWatch Logs via the EKS Fluent Bit DaemonSet:
```
Pod stdout → Fluent Bit DaemonSet → CloudWatch Log Group → Insights queries / alarms
```

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

---
## Design Focus

This project intentionally prioritises:
- clear separation of concerns
- auditability of operations
- secure-by-default configuration
- extensibility of integrations

over feature completeness.