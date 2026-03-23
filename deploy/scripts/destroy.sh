#!/usr/bin/env bash
# deploy/scripts/destroy.sh
# Destroys all AWS resources: EKS cluster + ECR repository
# Usage: ./deploy/scripts/destroy.sh
set -euo pipefail

REGION="${AWS_REGION:-eu-west-2}"
CLUSTER_NAME="operational-assistant-eks"
ECR_REPO="operational-assistant"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
step() { echo -e "\n${YELLOW}==> $1${NC}"; }

echo -e "${RED}"
echo "════════════════════════════════════════════════"
echo "  WARNING: This will DELETE all AWS resources"
echo "  - EKS cluster: $CLUSTER_NAME"
echo "  - ECR repository: $ECR_REPO (all images)"
echo "  Region: $REGION"
echo "════════════════════════════════════════════════"
echo -e "${NC}"

read -r -p "Are you sure? Type 'yes' to confirm: " confirm
[[ "$confirm" == "yes" ]] || { echo "Cancelled."; exit 0; }

step "Deleting EKS cluster '$CLUSTER_NAME' (~10 minutes)..."
if eksctl get cluster --name "$CLUSTER_NAME" --region "$REGION" &>/dev/null; then
  eksctl delete cluster --name "$CLUSTER_NAME" --region "$REGION"
  ok "EKS cluster deleted"
else
  echo "Cluster not found, skipping"
fi

step "Deleting ECR repository '$ECR_REPO'..."
if aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" &>/dev/null; then
  aws ecr delete-repository --repository-name "$ECR_REPO" --region "$REGION" --force > /dev/null
  ok "ECR repository deleted"
else
  echo "ECR repository not found, skipping"
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  All resources deleted. AWS billing stopped.${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"