#!/bin/bash

REGION="${region}"
SECRET_NAME="${cert_secret}"
ACM_ARN="${acm_arn}"

mkdir -p /var/log
LOG_FILE="/var/log/asg-cert-setup.log"
touch "$LOG_FILE" || LOG_FILE="/tmp/asg-cert-setup.log"
exec >> "$LOG_FILE" 2>&1
echo "==== ASG EC2 Certificate Setup Script Started at $(date) ===="

echo "REGION: $REGION"
echo "SECRET_NAME: $SECRET_NAME"
echo "ACM_ARN: $ACM_ARN"

# Install jq if missing
if command -v jq >/dev/null 2>&1; then
    echo "jq already installed."
else
    echo "jq not found. Attempting to install..."
    yum install -y jq && echo "jq installed." || echo "jq installation failed. Continuing without it."
fi

# Create target directories
mkdir -p /etc/ssl/private
mkdir -p /etc/ssl/certs

# Fetch and write private key
if [[ -n "$REGION" && -n "$SECRET_NAME" ]]; then
    echo "Fetching private key from Secrets Manager..."
    aws secretsmanager get-secret-value \
        --region "$REGION" \
        --secret-id "$SECRET_NAME" \
        --query SecretString \
        --output text > /etc/ssl/private/app.key

    if [[ -s /etc/ssl/private/app.key ]]; then
        echo "Private key saved to /etc/ssl/private/app.key"
        chmod 600 /etc/ssl/private/app.key
    else
        echo " Failed to write private key file"
    fi
else
    echo "Missing REGION or SECRET_NAME — skipping private key setup."
fi

# Fetch and write fullchain certificate
if [[ -n "$REGION" && -n "$ACM_ARN" ]]; then
    echo "Fetching certificate and chain from ACM..."
    CERT_DATA=$(aws acm get-certificate \
        --region "$REGION" \
        --certificate-arn "$ACM_ARN" \
        --query "{cert:Certificate, chain:CertificateChain}" \
        --output json)

    CERT_CONTENT=$(echo "$CERT_DATA" | jq -r '.cert')
    CHAIN_CONTENT=$(echo "$CERT_DATA" | jq -r '.chain')

    if [[ -n "$CERT_CONTENT" && -n "$CHAIN_CONTENT" ]]; then
        echo "$CERT_CONTENT" > /etc/ssl/certs/fullchain.pem
        echo "$CHAIN_CONTENT" >> /etc/ssl/certs/fullchain.pem
        chmod 644 /etc/ssl/certs/fullchain.pem
        echo "Certificate and chain written to /etc/ssl/certs/fullchain.pem"
    else
        echo "Failed to extract cert or chain from ACM"
    fi
else
    echo "Missing REGION or ACM_ARN — skipping fullchain setup."
fi

echo "==== ASG EC2 Certificate Setup Script Completed at $(date) ===="
