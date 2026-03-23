#!/usr/bin/env bash
# deploy/scripts/bootstrap.sh
# One-command setup: ECR + Docker build/push + EKS cluster + K8s deploy
# Usage: ./deploy/scripts/bootstrap.sh
set -euo pipefail

REGION="${AWS_REGION:-eu-west-2}"
CLUSTER_NAME="operational-assistant-eks"
ECR_REPO="operational-assistant"
NAMESPACE="operational-assistant"
NODE_TYPE="${NODE_TYPE:-t3.small}"
NODES="${NODES:-1}"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; exit 1; }
step() { echo -e "\n${YELLOW}==> $1${NC}"; }

step "Checking prerequisites..."
for cmd in aws docker eksctl kubectl; do
  command -v "$cmd" &>/dev/null || fail "$cmd is not installed. See README."
done
aws sts get-caller-identity &>/dev/null || fail "AWS credentials not configured. Run: aws configure"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ok "AWS account: $ACCOUNT_ID (region: $REGION)"

step "Creating ECR repository..."
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" &>/dev/null \
  && warn "ECR repository already exists, skipping" \
  || aws ecr create-repository --repository-name "$ECR_REPO" --region "$REGION" > /dev/null
ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO"
ok "ECR repository ready: $ECR_URI"

step "Building Docker image (linux/amd64)..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
docker build --platform linux/amd64 -t "$ECR_REPO:latest" "$PROJECT_ROOT"
ok "Docker image built"

step "Pushing image to ECR..."
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
docker tag "$ECR_REPO:latest" "$ECR_URI:latest"
docker push "$ECR_URI:latest"
ok "Image pushed to $ECR_URI:latest"

step "Creating EKS cluster '$CLUSTER_NAME' (~15 minutes)..."
if eksctl get cluster --name "$CLUSTER_NAME" --region "$REGION" &>/dev/null; then
  warn "Cluster already exists, skipping creation"
else
  eksctl create cluster \
    --name "$CLUSTER_NAME" \
    --region "$REGION" \
    --nodegroup-name standard-workers \
    --node-type "$NODE_TYPE" \
    --nodes "$NODES" \
    --nodes-min 1 \
    --nodes-max 2 \
    --managed
fi
ok "EKS cluster ready"

step "Updating kubeconfig..."
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$REGION"
ok "kubeconfig updated"

step "Deploying application to Kubernetes..."
MANIFESTS="$PROJECT_ROOT/deploy/k8s"

kubectl apply -f "$MANIFESTS/namespace.yaml"
kubectl apply -f "$MANIFESTS/rbac.yaml"
kubectl apply -f "$MANIFESTS/configmap.yaml"

kubectl get secret operational-assistant-secrets -n "$NAMESPACE" &>/dev/null \
  && warn "Secret already exists, skipping" \
  || kubectl create secret generic operational-assistant-secrets \
       --from-literal=API_KEY=demo-key-123 \
       --from-literal=AWS_REGION="$REGION" \
       -n "$NAMESPACE"

sed "s|258083582728.dkr.ecr.eu-west-2.amazonaws.com/operational-assistant:latest|$ECR_URI:latest|g" \
  "$MANIFESTS/deployment.yaml" | kubectl apply -f -

kubectl apply -f "$MANIFESTS/service.yaml"
kubectl apply -f "$MANIFESTS/networkpolicy.yaml"

kubectl rollout status deployment/operational-assistant -n "$NAMESPACE" --timeout=120s
ok "Application deployed"

echo ""
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Deployment complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo ""
kubectl get pods -n "$NAMESPACE"
echo ""
echo "Test the app:"
echo "  kubectl port-forward -n $NAMESPACE svc/operational-assistant-svc 8080:80"
echo "  curl http://localhost:8080/health"
echo ""
echo -e "${YELLOW}⚠️  Don't forget to destroy when done: ./deploy/scripts/destroy.sh${NC}"