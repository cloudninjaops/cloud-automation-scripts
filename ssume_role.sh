# Assume the role using sts:assume-role
TEMP_CREDS=$(aws sts assume-role \
  --role-arn "$ROLE_ARN" \
  --role-session-name "$SESSION_NAME" \
  --query "Credentials" \
  --output json)

# Extract the temporary credentials using jq
AWS_ACCESS_KEY_ID=$(echo "$TEMP_CREDS" | jq -r '.AccessKeyId')
AWS_SECRET_ACCESS_KEY=$(echo "$TEMP_CREDS" | jq -r '.SecretAccessKey')
AWS_SESSION_TOKEN=$(echo "$TEMP_CREDS" | jq -r '.SessionToken')

# Export the temporary credentials as environment variables
export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_SESSION_TOKEN

# Unset the temporary credentials
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN

echo "VPC deletion script completed, temporary credentials cleared."