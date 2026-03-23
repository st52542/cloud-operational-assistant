#!/usr/bin/env bash
# deploy/scripts/apply.sh
# Apply all K8s manifests in order. Intended for local development or manual deploys.
# Usage: ./deploy/scripts/apply.sh <image-uri>
set -euo pipefail

IMAGE_URI="${1:-123456789.dkr.ecr.eu-west-1.amazonaws.com/operational-assistant:latest}"
NAMESPACE="operational-assistant"
MANIFESTS_DIR="$(dirname "$0")/../k8s"

echo "==> Applying namespace and RBAC..."
kubectl apply -f "${MANIFESTS_DIR}/namespace.yaml"
kubectl apply -f "${MANIFESTS_DIR}/rbac.yaml"

echo "==> Applying ConfigMap..."
kubectl apply -f "${MANIFESTS_DIR}/configmap.yaml"

echo "==> Applying Deployment..."
kubectl apply -f "${MANIFESTS_DIR}/deployment.yaml"

echo "==> Updating image to: ${IMAGE_URI}"
kubectl set image deployment/operational-assistant \
  operational-assistant="${IMAGE_URI}" \
  -n "${NAMESPACE}"

echo "==> Applying Service, Ingress, NetworkPolicy..."
kubectl apply -f "${MANIFESTS_DIR}/service.yaml"
kubectl apply -f "${MANIFESTS_DIR}/ingress.yaml"
kubectl apply -f "${MANIFESTS_DIR}/networkpolicy.yaml"

echo "==> Waiting for rollout..."
kubectl rollout status deployment/operational-assistant \
  -n "${NAMESPACE}" --timeout=120s

echo "==> Done. Pods:"
kubectl get pods -n "${NAMESPACE}"
