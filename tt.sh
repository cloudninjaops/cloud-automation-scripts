#!/bin/bash
set -e

REGION="${region}"
SECRET_NAME="${cert_secret}"
ACM_ARN="${acm_arn}"

LOG_FILE="/var/log/asg_cert_setup.log"
mkdir -p /var/log
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[INFO] Starting certificate setup at $(date)"

# 1. Download Private Key from Secrets Manager
echo "[INFO] Fetching private key from Secrets Manager: $SECRET_NAME"
SECRET_JSON=$(aws secretsmanager get-secret-value \
  --secret-id "$SECRET_NAME" \
  --region "$REGION" \
  --query SecretString \
  --output text)

if [ $? -ne 0 ]; then
  echo "[ERROR] Failed to retrieve secret: $SECRET_NAME"
  exit 1
fi

# Assume the secret contains { "key": "...private key content..." }
PRIVATE_KEY=$(echo "$SECRET_JSON" | jq -r '.key')

if [ -z "$PRIVATE_KEY" ] || [ "$PRIVATE_KEY" == "null" ]; then
  echo "[ERROR] Private key not found in secret"
  exit 1
fi

echo "$PRIVATE_KEY" > /etc/ssl/private/app_key.pem
chmod 600 /etc/ssl/private/app_key.pem

# 2. Download certificate from ACM
echo "[INFO] Exporting ACM certificate: $ACM_ARN"
CERT_EXPORT=$(aws acm get-certificate \
  --certificate-arn "$ACM_ARN" \
  --region "$REGION")

if [ $? -ne 0 ]; then
  echo "[ERROR] Failed to retrieve ACM certificate"
  exit 1
fi

echo "$CERT_EXPORT" | jq -r '.Certificate' > /etc/ssl/certs/app_cert.pem
echo "$CERT_EXPORT" | jq -r '.CertificateChain' >> /etc/ssl/certs/app_cert.pem

chmod 644 /etc/ssl/certs/app_cert.pem

# 3. Final log
echo "[SUCCESS] Certificate and key setup completed at $(date)"
