# Load and validate techstack from JSON if it exists
OUTPUT_JSON_FILE="../account_policy/techstack_output.json"

if [ -f "$OUTPUT_JSON_FILE" ]; then
  if ! command -v jq >/dev/null 2>&1; then
    echo "jq is not installed. Skipping techstack comparison and proceeding..."
  else
    TECHSTACK_FROM_JSON=$(jq -r '.techstack' "$OUTPUT_JSON_FILE" | tr '[:upper:]' '[:lower:]')
    TECHSTACK_ARG_LOWER=$(echo "$TECH_STACK" | tr '[:upper:]' '[:lower:]')

    if [ "$TECHSTACK_FROM_JSON" != "$TECHSTACK_ARG_LOWER" ]; then
      echo "Tech stack mismatch: Expected '$TECHSTACK_FROM_JSON' but received '$TECHSTACK_ARG_LOWER'. Skipping execution."
      exit 0
    fi

    echo "Tech stack matched: $TECH_STACK. Proceeding with baseline script..."
  fi
else
  echo "techstack_output.json not found. Proceeding with original script logic..."
fi
