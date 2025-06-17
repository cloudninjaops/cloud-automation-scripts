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


resource "local_file" "techstack_output" {
  filename = "${path.module}/account_policy/techstack_output.json"

  content = jsonencode({
    techstack          = lower(var.techstack_name)
    tfc_workspace_name = var.TFC_WORKSPACE_NAME
    tfc_run_id         = var.TFC_RUN_ID
  })

  file_permission = "0644"
}

find . -type f -name "*.tf.disable" -exec bash -c 'mv "$0" "${0%.tf.disable}.tf"' {} \;
