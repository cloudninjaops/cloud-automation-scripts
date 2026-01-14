#!/usr/bin/bash
set -euo pipefail

# ------------------------------------------------------------
# Terraform external data source helper:
# - Reads JSON from stdin (jq)
# - Assumes role into target account
# - Imports cert into ACM
# - Returns {"arn": "..."} to Terraform
#
# FIX INCLUDED:
#   Handles "certificate field contains more than one certificate"
#   by ensuring:
#     --certificate       = ONLY leaf cert (1 PEM block)
#     --certificate-chain = intermediate chain (0+ PEM blocks)
# ------------------------------------------------------------

# 1) Read input from Terraform stdin
eval "$(
  jq -r '@sh "ACCOUNT_ID=\(.aws_account_id) REGION=\(.region) CERT_BODY=\(.cert_body) PRIV_KEY=\(.priv_key) CERT_CHAIN=\(.cert_chain) TAGS_JSON=\(.tags)"'
)"

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/Fepoc-All-Terraform-Role"
SESSION_NAME="ACMImportSession"

# 2) Assume the role
TEMP_CREDS="$(
  aws sts assume-role \
    --role-arn "$ROLE_ARN" \
    --role-session-name "$SESSION_NAME" \
    --query "Credentials" \
    --output json \
    --region "$REGION"
)"

export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_SESSION_TOKEN

AWS_ACCESS_KEY_ID="$(echo "$TEMP_CREDS" | jq -r '.AccessKeyId')"
AWS_SECRET_ACCESS_KEY="$(echo "$TEMP_CREDS" | jq -r '.SecretAccessKey')"
AWS_SESSION_TOKEN="$(echo "$TEMP_CREDS" | jq -r '.SessionToken')"

# 3) Format tags for AWS CLI (Key=string,Value=string)
# Terraform typically passes tags as JSON object: {"k1":"v1","k2":"v2"}
FORMATTED_TAGS="$(
  echo "${TAGS_JSON:-{}}" | jq -r 'to_entries | map("Key=\(.key),Value=\(.value)") | join(" ")'
)"

# -------------------------------
# 4) FIX: ensure leaf vs chain
# -------------------------------

# Normalize CRLF to LF (sometimes cert material has \r\n)
CERT_BODY="$(printf "%s\n" "${CERT_BODY:-}" | sed 's/\r$//')"
PRIV_KEY="$(printf "%s\n" "${PRIV_KEY:-}"  | sed 's/\r$//')"
CERT_CHAIN="$(printf "%s\n" "${CERT_CHAIN:-}" | sed 's/\r$//')"

CERT_COUNT="$(printf "%s\n" "$CERT_BODY" | grep -c "BEGIN CERTIFICATE" || true)"

if [ "${CERT_COUNT}" -gt 1 ]; then
  echo "INFO: CERT_BODY contains ${CERT_COUNT} certificates. Splitting leaf vs chain..." 1>&2

  # First PEM block = leaf cert
  LEAF_CERT="$(printf "%s\n" "$CERT_BODY" | awk '
    BEGIN{c=0}
    /BEGIN CERTIFICATE/{c++}
    { if(c==1) print }
    /END CERTIFICATE/{ if(c==1) exit }
  ')"

  # Remaining PEM blocks = extra chain
  REST_CERTS="$(printf "%s\n" "$CERT_BODY" | awk '
    BEGIN{c=0;out=0}
    /BEGIN CERTIFICATE/{c++; if(c>=2) out=1}
    { if(out) print }
  ')"

  CERT_BODY="$LEAF_CERT"

  # If CERT_CHAIN is empty, populate it from REST_CERTS.
  # If CERT_CHAIN is already provided, keep it to avoid duplicates.
  if [ -z "${CERT_CHAIN}" ] && [ -n "${REST_CERTS}" ]; then
    CERT_CHAIN="$REST_CERTS"
  fi
fi

# Write to temp files (more reliable than passing multiline strings)
CERT_FILE="$(mktemp)"
KEY_FILE="$(mktemp)"
CHAIN_FILE="$(mktemp)"

cleanup() {
  rm -f "$CERT_FILE" "$KEY_FILE" "$CHAIN_FILE"
}
trap cleanup EXIT

printf "%s\n" "$CERT_BODY" > "$CERT_FILE"
printf "%s\n" "$PRIV_KEY"  > "$KEY_FILE"
printf "%s\n" "$CERT_CHAIN" > "$CHAIN_FILE"

# Optional sanity logs (to stderr so Terraform doesn't treat as JSON output)
echo "INFO: leaf cert blocks:  $(grep -c 'BEGIN CERTIFICATE' "$CERT_FILE" 2>/dev/null || true)" 1>&2
echo "INFO: chain cert blocks: $(grep -c 'BEGIN CERTIFICATE' "$CHAIN_FILE" 2>/dev/null || true)" 1>&2

# 5) Import certificate
# Only pass --certificate-chain if chain file is non-empty
if [ -s "$CHAIN_FILE" ]; then
  CERT_ARN="$(
    aws acm import-certificate \
      --certificate fileb://"$CERT_FILE" \
      --private-key fileb://"$KEY_FILE" \
      --certificate-chain fileb://"$CHAIN_FILE" \
      --tags $FORMATTED_TAGS \
      --region "$REGION" \
      --query 'CertificateArn' \
      --output text
  )"
else
  CERT_ARN="$(
    aws acm import-certificate \
      --certificate fileb://"$CERT_FILE" \
      --private-key fileb://"$KEY_FILE" \
      --tags $FORMATTED_TAGS \
      --region "$REGION" \
      --query 'CertificateArn' \
      --output text
  )"
fi

# 6) Unset temporary credentials
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN

# 7) Output JSON for Terraform external data source
jq -n --arg arn "$CERT_ARN" '{"arn":$arn}'
