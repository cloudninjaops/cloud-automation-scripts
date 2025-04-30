#!/bin/bash
set -e

ACCOUNT_ID="$1"
KMS_KEY_ID="$2"
REGION="$3"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/Fepoc-All-Terraform-Role"
POLICY_FILE="current_policy.json"
UPDATED_FILE="updated_policy.json"

# Fetch current policy
aws kms get-key-policy \
  --key-id "$KMS_KEY_ID" \
  --policy-name default \
  --output text \
  --region "$REGION" > "$POLICY_FILE"

# Display fetched policy
echo "--- Current KMS Policy ---"
cat "$POLICY_FILE"

# Modify policy with new role
jq --arg role "$ROLE_ARN" '
  .Statement |= map(
    if .Sid == "AllowExternalAccountUse" then
      .Principal.AWS |= (
        if type == "array" then
          if index($role) == null then . + [$role] else . end
        else
          if . == $role then . else [$role, .] end
        end
      )
    else .
    end
  )
' "$POLICY_FILE" > "$UPDATED_FILE"

# If policy unchanged, skip update
if cmp -s "$POLICY_FILE" "$UPDATED_FILE"; then
  echo "[INFO] No update performed. Role already exists: $ROLE_ARN"
else
  echo "--- Updated KMS Policy ---"
  cat "$UPDATED_FILE"

  # Apply updated policy
  aws kms put-key-policy \
    --key-id "$KMS_KEY_ID" \
    --policy-name default \
    --policy file://"$UPDATED_FILE" \
    --region "$REGION"
fi
