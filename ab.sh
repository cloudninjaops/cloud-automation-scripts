#!/bin/bash
set -e

REGION="${region}"
SECRET_NAME="${cert_secret}"
ACM_ARN="${acm_arn}"
LOG_FILE="/var/log/asg_cert_setup.log"

exec > >(tee -a "$LOG_FILE") 2>&1
echo "[INFO] Starting cert setup at $(date)"

# -------- Fetch private key from Secrets Manager --------
echo "[INFO] Fetching private key from Secrets Manager: $SECRET_NAME"

SECRET_OUTPUT=$(aws secretsmanager get-secret-value \
  --region "$REGION" \
  --secret-id "$SECRET_NAME" \
  --query SecretString \
  --output text)

if [ -z "$SECRET_OUTPUT" ]; then
  echo "[ERROR] Secret retrieval failed or returned empty"
  exit 1
fi

# Parse raw private key from plain JSON without jq
PRIVATE_KEY=$(echo "$SECRET_OUTPUT" | grep -o '"key"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d':' -f2- | tr -d ' "' | sed 's/\\n/\n/g')

if [ -z "$PRIVATE_KEY" ]; then
  echo "[ERROR] Failed to extract private key from secret JSON"
  exit 1
fi

mkdir -p /etc/ssl/private
echo -e "$PRIVATE_KEY" > /etc/ssl/private/app_key.pem
chmod 600 /etc/ssl/private/app_key.pem

# -------- Fetch certificate from ACM --------
echo "[INFO] Fetching certificate from ACM: $ACM_ARN"

CERT_JSON=$(aws acm get-certificate \
  --region "$REGION" \
  --certificate-arn "$ACM_ARN")

if [ -z "$CERT_JSON" ]; then
  echo "[ERROR] ACM cert retrieval failed"
  exit 1
fi

CERT_BODY=$(echo "$CERT_JSON" | grep -oP '(?<="Certificate": ")[^"]*')
CHAIN_BODY=$(echo "$CERT_JSON" | grep -oP '(?<="CertificateChain": ")[^"]*')

if [ -z "$CERT_BODY" ]; then
  echo "[ERROR] Certificate body missing"
  exit 1
fi

mkdir -p /etc/ssl/certs
echo "$CERT_BODY" > /etc/ssl/certs/app_cert.pem
[ -n "$CHAIN_BODY" ] && echo "$CHAIN_BODY" >> /etc/ssl/certs/app_cert.pem
chmod 644 /etc/ssl/certs/app_cert.pem

echo "[SUCCESS] SSL cert and key setup complete at $(date)"
