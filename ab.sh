#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# TOP PART: Read Terraform external input safely (handles:
#  - normal JSON object
#  - JSON object wrapped as a string (escaped)
#  - tags passed as JSON string; decodes to object
# ------------------------------------------------------------

# 1) Read raw stdin from Terraform
INPUT_RAW="$(cat)"

# 2) Decode stdin if it is a JSON string (can be double-encoded)
INPUT_JSON="$INPUT_RAW"
while echo "$INPUT_JSON" | jq -e 'type=="string"' >/dev/null 2>&1; do
  INPUT_JSON="$(echo "$INPUT_JSON" | jq -r '.')"
done

# 3) Ensure we ended up with a JSON object
if ! echo "$INPUT_JSON" | jq -e 'type=="object"' >/dev/null 2>&1; then
  echo "ERROR: Terraform input is not a JSON object after decoding." >&2
  echo "DEBUG: INPUT_RAW:  $INPUT_RAW" >&2
  echo "DEBUG: INPUT_JSON: $INPUT_JSON" >&2
  exit 5
fi

# 4) Extract required fields
ACCOUNT_ID="$(echo "$INPUT_JSON" | jq -r '.aws_account_id // empty')"
REGION="$(echo "$INPUT_JSON" | jq -r '.region // empty')"
CERT_BODY="$(echo "$INPUT_JSON" | jq -r '.cert_body // empty')"
PRIV_KEY="$(echo "$INPUT_JSON" | jq -r '.priv_key // empty')"
CERT_CHAIN="$(echo "$INPUT_JSON" | jq -r '.cert_chain // ""')"

# tags is typically passed as a STRING (because external query values are strings)
# so read it as raw string; default to "{}"
TAGS_JSON="$(echo "$INPUT_JSON" | jq -r '.tags // "{}"')"

# 5) Basic validation
if [ -z "$ACCOUNT_ID" ] || [ -z "$REGION" ]; then
  echo "ERROR: Missing aws_account_id or region in input JSON" >&2
  echo "DEBUG: INPUT_JSON: $INPUT_JSON" >&2
  exit 5
fi

# 6) Normalize TAGS_JSON -> TAGS_NORM (must be a JSON object)
# TAGS_JSON might be:
#  - {"k":"v"}                 (object text)
#  - "{\"k\":\"v\"}"           (escaped)
#  - "{"k":"v"}"               (quoted)
TAGS_NORM="$TAGS_JSON"

# If it's quoted JSON, decode until it's not a string
while echo "$TAGS_NORM" | jq -e 'type=="string"' >/dev/null 2>&1; do
  TAGS_NORM="$(echo "$TAGS_NORM" | jq -r '.')"
done

# Validate it's an object; else default to empty object
if ! echo "$TAGS_NORM" | jq -e 'type=="object"' >/dev/null 2>&1; then
  echo "WARN: tags is not a JSON object after decode. Defaulting to {}." >&2
  echo "DEBUG: TAGS_JSON: $TAGS_JSON" >&2
  TAGS_NORM='{}'
fi

# 7) Convert tags to AWS CLI format (force values to string)
FORMATTED_TAGS="$(
  echo "$TAGS_NORM" | jq -r '
    to_entries
    | map(select(.value != null))
    | map("Key=\(.key),Value=\(.value|tostring)")
    | join(" ")
  '
)"

# ---- From here continue with ROLE_ARN, assume-role, leaf/chain split, import, etc. ----
