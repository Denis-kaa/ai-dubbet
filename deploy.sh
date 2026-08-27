#!/bin/bash

#!/bin/bash

# AI Dubber Deployment Script for Ubuntu Server
# This script deploys the frontend, backend, and configures services with CLI input

set -e

echo "=== AI Dubber Deployment Script ==="
echo "Target: 51.21.35.247"
echo "Deploy Directory: /opt/xadichai"
echo ""

DEPLOY_DIR="/opt/xadichai"

read -sp "Enter SSH key password (if any): " SSH_PASS
echo ""

read -p "Enter OPENAI_API_KEY: " OPENAI_API_KEY
read -p "Enter AZURE_SPEECH_KEY: " AZURE_SPEECH_KEY
read -p "Enter CLICK_MERCHANT_ID (optional): " CLICK_MERCHANT_ID
read -p "Enter CLICK_SERVICE_ID (optional): " CLICK_SERVICE_ID
read -sp "Enter CLICK_SECRET_KEY (optional): " CLICK_SECRET_KEY
echo ""

echo "=== Starting Local Deployment, will SSH to remote server ==="
