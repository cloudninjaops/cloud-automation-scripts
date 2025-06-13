#!/bin/bash

VPCE_ID="$1"

if [ -z "$VPCE_ID" ]; then
  echo "Usage: $0 <vpc-endpoint-id>"
  exit 1
fi

echo "Trying to enable private DNS for VPC Endpoint: $VPCE_ID"
echo "Waiting up to 10 minutes for the resource to become available..."

MAX_WAIT=600
SLEEP_INTERVAL=10
ELAPSED=0

while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
  STATUS=$(aws ec2 describe-vpc-endpoints \
    --vpc-endpoint-ids "$VPCE_ID" \
    --query "VpcEndpoints[0].State" \
    --output text 2>/dev/null)

  echo "Status: $STATUS (elapsed: ${ELAPSED}s)"

  if [ "$STATUS" = "available" ]; then
    echo "VPC Endpoint is available. Enabling Private DNS..."

    aws ec2 modify-vpc-endpoint \
      --vpc-endpoint-id "$VPCE_ID" \
      --private-dns-enabled \
    && echo "✅ Private DNS enabled successfully." \
    || echo "⚠️  Warning: Failed to enable Private DNS. It may already be enabled or not supported."

    exit 0
  fi

  sleep "$SLEEP_INTERVAL"
  ELAPSED=$((ELAPSED + SLEEP_INTERVAL))
done

echo "❌ Timeout: VPC Endpoint did not reach 'available' state in 10 minutes."
exit 0  # optional action, not failing Terraform
