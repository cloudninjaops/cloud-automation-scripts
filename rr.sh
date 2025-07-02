#!/bin/bash

REGION="${region}"
SECRET_NAME="${cert_secret}"
ACM_ARN="${acm_arn}"

# Setup log file
mkdir -p /var/log
LOG_FILE="/var/log/asg-cert-setup.log"
touch "$LOG_FILE" || LOG_FILE="/tmp/asg-cert-setup.log"

# Logging function: echo to console and log file
log() {
  echo "$@" | tee -a "$LOG_FILE"
}

log "==== ASG EC2 Certificate Setup Script Started at $(date) ===="

log "REGION: $REGION"
log "SECRET_NAME: $SECRET_NAME"
log "ACM_ARN: $ACM_ARN"

# Install jq if missing
if command -v jq >/dev/null 2>&1; then
  log "jq already installed."
else
  log "jq not found. Installing..."
  yum install -y jq && log "jq installation successful." || log "jq installation failed. Continuing anyway."
fi

# Create required directories
mkdir -p /etc/ssl/private
mkdir -p /etc/ssl/certs

# Fetch private key from Secrets Manager
if [[ -n "$REGION" && -n "$SECRET_NAME" ]]; then
  log "Fetching private key from Secrets Manager..."
  aws secretsmanager get-secret-value \
    --region "$REGION" \
    --secret-id "$SECRET_NAME" \
    --query SecretString \
    --output text > /etc/ssl/private/app.key

  if [[ -s /etc/ssl/private/app.key ]]; then
    chmod 600 /etc/ssl/private/app.key
    log "Private key saved to /etc/ssl/private/app.key"
  else
    log "Failed to save private key"
  fi
else
  log "Missing REGION or SECRET_NAME — skipping private key setup"
fi

# Fetch certificate and chain from ACM
if [[ -n "$REGION" && -n "$ACM_ARN" ]]; then
  log "Fetching certificate and chain from ACM..."
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
    log "Certificate and chain saved to /etc/ssl/certs/fullchain.pem"
  else
    log "Failed to extract cert or chain from ACM response"
  fi
else
  log "Missing REGION or ACM_ARN — skipping certificate setup"
fi

log "==== ASG EC2 Certificate Setup Script Completed at $(date) ===="
