# ──────────────────────────────────────────────────────────────────────────────
# Ad-Hoc Tagging for Terraform Workspace Resources
# ──────────────────────────────────────────────────────────────────────────────
# This file defines tagging rules for AWS resources.
# It supports two modes:
#   1. Workspace mode  — applies tags to ALL resources in a TFC workspace
#   2. Tagset mode     — applies tags to specific resources listed below
# Both modes can be used together in the same run.
#
# Instructions:
#   - Update 'config' block with your AWS account details
#   - Add 'workspace' block if you want to tag all resources in a TFC workspace
#   - Add 'tagsets' block for targeted tagging of specific resources
#   - All tag values must be strings — wrap numbers in quotes e.g. "100"
#   - ARNs must be full valid AWS ARNs
#   - Instance IDs support EC2, Security Groups, EBS volumes, VPC Endpoints
#   - Commit and push this file to trigger a new tagging run in TFC
# ──────────────────────────────────────────────────────────────────────────────

tagging:

  # ── Config block (required) ────────────────────────────────────────────────
  # Contains AWS account details and cross-account role for tagging operations.
  config:
    account_id:      "123456789012"                                         # AWS Account ID where resources live
    region:          "us-east-1"                                            # AWS region — defaults to us-east-1 if not provided
    target_role_arn: "arn:aws:iam::123456789012:role/adhoc-tagging-role"    # IAM role to assume in target account — optional, defaults to arn:aws:iam::<account_id>:role/xyz

  # ── Workspace block (optional) ─────────────────────────────────────────────
  # Provide this block if you want to tag ALL resources managed by a TFC workspace.
  # Tags defined here are applied to every resource found in the workspace state file.
  # Remove or comment out this block if you only want to use tagsets below.
  workspace:
    name: "step_functions_ut"                 # TFC workspace name to read state from
    tags:
      cost_center:    "1000"                  # Cost center code for finance reporting
      billing_code:   "BC-2026"               # Billing code for cost allocation
      environment:    "sandbox"               # Environment type e.g. sandbox, dev, staging, prod
      managed_by:     "terraform"             # Indicates resource is managed by Terraform

  # ── Tagsets block (optional) ───────────────────────────────────────────────
  # Each tagset applies a specific set of tags to a specific list of resources.
  # You can have as many tagsets as needed — each is processed independently.
  # Remove or comment out this block if you only want to use workspace mode above.
  tagsets:

    # Tagset 1 — Apply optimization/delete schedule tag to S3 buckets
    # Use case: mark buckets scheduled for deletion after a certain date
    - name: optimize_delete
      tags:
        Optimize-DELETE: "05-2027"            # Date after which resource can be deleted
      resources_list:
        s3_buckets:
          - test-ami-export-test           # S3 bucket name only — no ARN needed
          - test-ami-import-test

    # Tagset 2 — Apply rightsizing tag to EC2 instances
    # Use case: mark instances flagged for rightsizing review
    - name: optimize_rightsize
      tags:
        Optimize-RIGHTSIZE: "05-2027"         # Date by which rightsizing should be completed
      resources_list:
        instance_ids:
          - i-12344511111111111              # EC2 instance ID
          - i-98765411111111111              # Supports: EC2 (i-), SG (sg-), EBS (vol-), VPCE (vpce-)

    # Tagset 3 — Apply backup policy tag to specific EC2 instances
    # Use case: mark instances that require daily backup
    - name: backup_policy
      tags:
        backup_schedule:  "daily"             # Backup frequency
        retention_days:   "30"               # Number of days to retain backups
      resources_list:
        instance_ids:
          - i-12344511111111111   
          - i-98765411111111111

    # Tagset 4 — Apply cost allocation tags to mixed resource types
    # Use case: apply cost center and billing code to specific resources
    # that are NOT managed by the workspace above
    - name: cost_allocation
      tags:
        cost_center:    "2000"               # Override cost center for these specific resources
        billing_code:   "BC-PROJ-99"         # Project-specific billing code
        team:           "platform"           # Team responsible for these resources
      resources_list:
        arns:
          # Use full ARNs for any AWS service supported by Resource Groups Tagging API
          - arn:aws:sqs:us-east-1:123456789012:test-app.fifo
          - arn:aws:lambda:us-east-1:123456789012:function:test-lbdapp-01
          - arn:aws:rds:us-east-1:123456789012:db:my-rds-instance
          - arn:aws:sns:us-east-1:123456789012:my-sns-topic
        instance_ids:
          # EC2 family resource IDs — ARN not needed, script constructs it
          - i-12344511111111111   
          - i-98765411111111111
        s3_buckets:
          # S3 bucket names only — not ARNs
          - my-app-data-bucket
          - my-logs-bucket
        iam_arns:
          # Full IAM ARNs — supports roles and policies
          - arn:aws:iam::123456789012:role/service-role/my-lambda-role
          - arn:aws:iam::123456789012:policy/my-custom-policy