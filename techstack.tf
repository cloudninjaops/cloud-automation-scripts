# ─── Write techstack_output.json ───────────────────────────────────────
echo "Writing techstack_output.json..."
OUTPUT_JSON_PATH="../account_policy/techstack_output.json"

cat <<EOF > $OUTPUT_JSON_PATH
{
  "techstack": "${TECH_STACK}",
  "tfc_workspace": "${TFC_WORKSPACE_NAME}",
  "tfc_run_id": "${TFC_RUN_ID}",
  "timestamp": "${TIMESTAMP}"
}
EOF

# ─── Add techstack_output.json to Git ──────────────────────────────────
git add "$OUTPUT_JSON_PATH" || exit 1
