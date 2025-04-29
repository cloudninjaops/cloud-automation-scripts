#!/bin/bash

set -e

# Input Variables
REGION=$1
KMS_KEY_ID=$2

if [[ -z "$REGION" || -z "$KMS_KEY_ID" ]]; then
  echo "Usage: $0 <region> <kms_key_id>"
  exit 1
fi

echo "Fetching latest golden AMI in region: $REGION..."

# 1. Get latest golden* AMI
LATEST_AMI_ID=$(aws ec2 describe-images \
  --region "$REGION" \
  --owners self \
  --filters "Name=name,Values=golden*" \
  --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
  --output text)

if [[ "$LATEST_AMI_ID" == "None" || -z "$LATEST_AMI_ID" ]]; then
  echo "No golden AMI found."
  exit 1
fi

echo "Latest Golden AMI ID: $LATEST_AMI_ID"

# 2. List AMI launch permissions
echo "Fetching accounts that have launch permissions on AMI..."

ACCOUNT_LIST=$(aws ec2 describe-image-attribute \
  --region "$REGION" \
  --image-id "$LATEST_AMI_ID" \
  --attribute launchPermission \
  --query 'LaunchPermissions[].UserId' \
  --output text)

if [[ -z "$ACCOUNT_LIST" ]]; then
  echo "AMI is not shared with any accounts."
else
  echo "AMI is shared with following account IDs:"
  for account in $ACCOUNT_LIST; do
    echo "  - $account"
  done
fi

# 3. Get current KMS Key policy
echo "Fetching current KMS Key policy..."

aws kms get-key-policy \
  --region "$REGION" \
  --key-id "$KMS_KEY_ID" \
  --policy-name default \
  --output json | jq '.'

echo "Done."
