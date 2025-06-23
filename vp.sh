# Waiting up to 10 minutes for the role to become available...
echo "Waiting up to 10 minutes for the role to become available..."

MAX_WAIT=600
SLEEP_INTERVAL=10
ELAPSED=0

while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
    ROLE_AVAILABLE=$(aws sts assume-role \
        --role-arn "$ROLE_ARN" \
        --role-session-name "$SESSION_NAME" \
        --region us-east-1 \
        --query 'Credentials.AccessKeyId' \
        --output text 2>/dev/null)

    echo "Checking role availability... (elapsed: ${ELAPSED}s)"

    if [ "$ROLE_AVAILABLE" != "None" ] && [ -n "$ROLE_AVAILABLE" ]; then
        echo "Role is available. Proceeding with the session."
        break
    fi

    sleep "$SLEEP_INTERVAL"
    ELAPSED=$((ELAPSED + SLEEP_INTERVAL))
done

if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
    echo "Timeout: Role did not become available within 10 minutes."
    exit 1
fi

echo "Done Sleeping.."