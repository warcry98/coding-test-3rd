#!/bin/bash

# Exit on error and undefined variables
set -euo pipefail

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%dT%H:%M:%S%z')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%dT%H:%M:%S%z')] ERROR: $1${NC}" >&2
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%dT%H:%M:%S%z')] WARNING: $1${NC}"
}

# Check required environment variables
required_vars=(
    "AWS_REGION"
    "AWS_ACCOUNT_ID"
    "ECS_CLUSTER"
    "ECR_REGISTRY"
    "ECR_REPOSITORY"
    "IMAGE_TAG"
)

for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        error "Required environment variable $var is not set"
        exit 1
    fi
done

# Check if we're in the right directory
if [[ ! -f "deployment/deploy.sh" ]]; then
    error "Please run this script from the project root directory"
    exit 1
fi

# Load environment variables
if [[ ! -f ".env.production" ]]; then
    error ".env.production file not found"
    exit 1
fi

source .env.production

# Function to check AWS commands
check_aws_command() {
    if ! aws sts get-caller-identity &>/dev/null; then
        error "AWS CLI not configured correctly. Please check your credentials."
        exit 1
    fi
}

# Build and push Docker image
{
    log "Building Docker image..."
    docker build -t fund-analysis:latest .

    log "Logging in to ECR..."
    aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

    log "Tagging image..."
    docker tag fund-analysis:latest "${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

    log "Pushing image to ECR..."
    docker push "${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"
} || {
    error "Failed to build or push Docker image"
    exit 1
}

# Update ECS task definition
log "Registering new task definition..."
TASK_DEF=$(aws ecs register-task-definition \
    --cli-input-json file://deployment/task-definition.json \
    --region "${AWS_REGION}") || {
    error "Failed to register task definition"
    exit 1
}

TASK_DEF_ARN=$(echo "$TASK_DEF" | jq -r '.taskDefinition.taskDefinitionArn')

if [[ -z "$TASK_DEF_ARN" ]]; then
    error "Failed to get task definition ARN"
    exit 1
fi

log "New task definition ARN: $TASK_DEF_ARN"

# Make a backup of service definition
cp deployment/service-definition.json deployment/service-definition.json.bak

# Update service definition with new task definition
sed -i "s|\${TASK_DEFINITION_ARN}|$TASK_DEF_ARN|g" deployment/service-definition.json

# Update or create ECS service
log "Checking for existing service..."
SERVICE_EXISTS=$(aws ecs describe-services \
    --cluster "${ECS_CLUSTER}" \
    --services fund-analysis \
    --region "${AWS_REGION}" \
    | jq -r '.services[] | select(.status != "INACTIVE") | .serviceName') || true

if [[ -z "$SERVICE_EXISTS" ]]; then
    log "Creating new ECS service..."
    aws ecs create-service \
        --cli-input-json file://deployment/service-definition.json \
        --region "${AWS_REGION}" || {
        error "Failed to create service"
        mv deployment/service-definition.json.bak deployment/service-definition.json
        exit 1
    }
else
    log "Updating existing ECS service..."
    aws ecs update-service \
        --cluster "${ECS_CLUSTER}" \
        --service fund-analysis \
        --task-definition "$TASK_DEF_ARN" \
        --force-new-deployment \
        --region "${AWS_REGION}" || {
        error "Failed to update service"
        mv deployment/service-definition.json.bak deployment/service-definition.json
        exit 1
    }
fi

# Restore service definition backup
mv deployment/service-definition.json.bak deployment/service-definition.json

# Wait for service to stabilize
log "Waiting for service to stabilize..."
aws ecs wait services-stable \
    --cluster "${ECS_CLUSTER}" \
    --services fund-analysis \
    --region "${AWS_REGION}" || {
    warn "Service took too long to stabilize. Please check the AWS console for status."
}

log "Deployment completed successfully!"