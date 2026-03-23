# Threat Model

## Scope

This document covers the security posture of the Cloud-native Operational Assistant running on AWS EKS. It uses a simplified STRIDE-adjacent analysis focused on the attack surfaces most relevant to a Kubernetes-hosted API service.

---

## Trust Boundary Diagram

```
                    [ Internet / Internal VPN ]
                               │
                    ┌──────────▼──────────┐
                    │   AWS ALB           │  ← TLS termination
                    │   (HTTPS only)      │
                    └──────────┬──────────┘
                               │  HTTP (internal)
                    ┌──────────▼──────────┐
                    │  K8s Ingress        │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
Trust boundary ──▶  │  Pod (app process)  │  ← UID 1001, read-only FS
                    │                     │
                    │  FastAPI + SQLite   │
                    └──────────┬──────────┘
                               │
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
         [ ConfigMap ]   [ K8s Secret ]   [ emptyDir /data ]
```

---

## Threat Analysis

### 1. Input API — Injection and Abuse

**Threat:** A caller sends a malformed or malicious `target_service` value (e.g. path traversal `../../etc/passwd`, SQL injection, shell metacharacters).

**Mitigations:**
- `target_service` is validated by Pydantic regex: only `[a-zA-Z0-9_\-\.]` characters are accepted. Any other input returns HTTP 422 before reaching the orchestration layer.
- `request_type` and `environment` are strict enums — only known values are accepted.
- The adapter layer receives the validated `target_service` string and uses it only as a lookup key or label in simulated responses, never as a filesystem path or shell argument.
- In production adapters (real HTTP calls to internal APIs), `target_service` must be validated against an allowlist before use in URLs or queries.

**Residual risk:** If a production adapter constructs URLs using `target_service` without additional allowlist validation, SSRF is possible. Mitigation: enforce an allowlist in each adapter.

---

### 2. Secrets Management

**Threat:** API keys or AWS credentials are committed to the Git repository or baked into the Docker image.

**Mitigations:**
- No secrets are hardcoded anywhere in the codebase. `deploy/k8s/secret.yaml` contains only `__REPLACED_BY_PIPELINE__` placeholders.
- Secrets are injected at deploy-time by the GitHub Actions pipeline from GitHub Encrypted Secrets.
- AWS access inside the pod uses IRSA (IAM Roles for Service Accounts) — no AWS access keys are present in the pod environment. The pod assumes an IAM role via the EKS OIDC provider.
- `.gitignore` excludes `.env` files and SQLite databases.

**Residual risk:** GitHub repository secrets are accessible to anyone with write access to the repository. Mitigate with branch protection rules and limiting `secrets.*` access to protected branches only.

---

### 3. Image Supply Chain

**Threat:** The Docker image is built from a compromised base image, contains known CVEs, or is tampered with between build and deployment.

**Mitigations:**
- The CI pipeline runs Trivy image scanning before any `docker push`. Builds with CRITICAL severity CVEs fail the pipeline.
- The image is built from `python:3.12-slim` — a minimal base image maintained by the Docker Official Images team.
- The multi-stage Dockerfile installs only packages listed in `requirements.txt` — no dev tools, no build chains in the final image.
- Images are tagged by Git commit SHA — no `latest`-only deployments in production (latest is pushed additionally as a convenience tag for local development only).
- The ECR repository should have image scanning enabled and immutable tags enforced.

**Residual risk:** Dependency scanning covers the Python packages in `requirements.txt` at build time, but not transitive C library vulnerabilities in the base image that Trivy may miss. Mitigate by adding `pip-audit` to the CI pipeline and subscribing to Python security advisories.

---

### 4. Privileges in the Cluster

**Threat:** A compromised pod is used to pivot across the cluster, access other namespaces, or escalate privileges.

**Mitigations:**
- The container runs as UID 1001 (non-root). `runAsNonRoot: true` is enforced at the pod spec level.
- `readOnlyRootFilesystem: true` — the container filesystem is immutable at runtime. Only `/data` and `/tmp` (emptyDir volumes) are writable.
- All Linux capabilities are dropped (`capabilities.drop: [ALL]`). `allowPrivilegeEscalation: false` prevents any `setuid` escalation.
- The ServiceAccount (`operational-assistant-sa`) has `automountServiceAccountToken: false`. It is bound to a minimal Role granting read access to ConfigMaps and Pods in its own namespace only.
- A NetworkPolicy restricts ingress to traffic from `kube-system` (the ingress controller) and restricts egress to DNS (port 53) and HTTPS (port 443). No east-west traffic to other namespaces is allowed.

**Residual risk:** The `emptyDir` volume for `/data` is readable by any process running as UID 1001 in the pod. If the SQLite database contains sensitive data, it should be encrypted at rest (e.g. using AWS EFS with KMS encryption instead of emptyDir).

---

### 5. Auditability

**Threat:** A malicious or erroneous operation is performed and there is no record of who requested it or what happened.

**Mitigations:**
- Every request generates a UUID `request_id` which is present in all log lines and all audit log entries.
- The audit log table records: `request_created`, `processing_started`, and `request_completed` / `request_failed` for every request, with timestamp and details.
- HTTP middleware logs every incoming request and outgoing response with method, path, status code, duration, and `request_id`.
- In production, stdout logs are forwarded to CloudWatch Logs with a 90-day retention policy. CloudWatch log groups should have `KMS` encryption enabled.
- Future: add caller identity (API key or IAM principal) to the `request_created` audit event once authentication is implemented.

**Residual risk:** The current MVP has no authentication. Any caller with network access to the Ingress can submit requests. In production, add at minimum an API key check or AWS SigV4 verification at the ALB level.

---

## Out of Scope (for MVP)

| Item | Status |
|---|---|
| Authentication / authorisation on API | Not implemented. Must be added before production use |
| mTLS between pods | Not configured. Consider a service mesh (Istio/Linkerd) |
| Secrets rotation | Manual. Future: AWS Secrets Manager + External Secrets Operator |
| OWASP Top 10 full assessment | Not performed. Recommend before any customer-facing exposure |
