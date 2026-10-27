#!/bin/bash
# ==============================================================================
# EC2 User Data (Cloud-Init) Script for Outpace Baseball
# Target OS: Ubuntu 24.04 LTS (Noble Numbat)
# ==============================================================================
# Note: Containers are ephemeral by design. Uploaded videos and analysis results
# are stored in Amazon S3 for durable persistence.
# ==============================================================================

set -euxo pipefail

# ------------------------------------------------------------------------------
# 1. Configuration (Set your environment placeholders)
# ------------------------------------------------------------------------------
AWS_S3_BUCKET_NAME="YOUR_BUCKET_NAME"
AWS_DEFAULT_REGION="YOUR_REGION"
REPO_URL="https://github.com/hirokuwa821/Outpace-Baseball-OpenCV-AI-Competition-2026.git"
BRANCH_NAME="aws-deploy"

APP_DIR="/opt/outpace-baseball"

# ------------------------------------------------------------------------------
# 2. Install Docker and System Dependencies
# ------------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    docker.io \
    git \
    curl \
    ca-certificates

systemctl enable --now docker

# Optional: Add ubuntu user to docker group
usermod -aG docker ubuntu || true

# ------------------------------------------------------------------------------
# 3. Clone Repository and Build Container Image
# ------------------------------------------------------------------------------
if [ -d "${APP_DIR}" ]; then
    cd "${APP_DIR}"
    git fetch origin
    git checkout "${BRANCH_NAME}"
    git pull origin "${BRANCH_NAME}"
else
    git clone -b "${BRANCH_NAME}" "${REPO_URL}" "${APP_DIR}"
    cd "${APP_DIR}"
fi

docker build -t outpace .

# ------------------------------------------------------------------------------
# 4. Run Application Container (Uses EC2 IAM Instance Role)
# ------------------------------------------------------------------------------
# Clean up any existing container
docker rm -f outpace-app 2>/dev/null || true

# Standard execution: Logs to local Docker container stdout/stderr
docker run -d \
    --name outpace-app \
    --restart unless-stopped \
    -p 80:8501 \
    -e AWS_S3_BUCKET_NAME="${AWS_S3_BUCKET_NAME}" \
    -e AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION}" \
    outpace

# ------------------------------------------------------------------------------
# OPTIONAL: CloudWatch Logs Integration
# ------------------------------------------------------------------------------
# If you wish to forward container logs to AWS CloudWatch Logs, ensure the EC2
# IAM role includes logs:CreateLogStream and logs:PutLogEvents, and pre-create
# the log group /ecs/outpace-baseball in AWS CloudWatch.
# Then replace the docker run command above with:
#
# docker run -d \
#     --name outpace-app \
#     --restart unless-stopped \
#     -p 80:8501 \
#     --log-driver=awslogs \
#     --log-opt awslogs-region="${AWS_DEFAULT_REGION}" \
#     --log-opt awslogs-group="/ecs/outpace-baseball" \
#     --log-opt awslogs-create-group=true \
#     -e AWS_S3_BUCKET_NAME="${AWS_S3_BUCKET_NAME}" \
#     -e AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION}" \
#     outpace
# ------------------------------------------------------------------------------

echo "Outpace Baseball deployment completed successfully."
