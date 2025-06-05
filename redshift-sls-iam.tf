data "aws_sts_caller_identity" "current" {}

data "aws_kms_key" "master" {
  key_id = var.kms_key_alias
}

# --------------------------------------------
# Role 1: AWSServiceRoleForRedshift
# --------------------------------------------
resource "aws_iam_role" "aws_service_role_for_redshift" {
  name = "AWSServiceRoleForRedshift"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = [
            "redshift.amazonaws.com",
            "redshift-serverless.amazonaws.com"
          ]
        },
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "attach_service_linked_policy" {
  role       = aws_iam_role.aws_service_role_for_redshift.name
  policy_arn = "arn:aws:iam::aws:policy/aws-service-role/AmazonRedshiftServiceLinkedRolePolicy"
}

# --------------------------------------------
# Role 2: AmazonRedshiftCommandsAccessRole
# --------------------------------------------
resource "aws_iam_role" "redshift_commands_access_role" {
  name = "AmazonRedshiftCommandsAccessRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = [
            "redshift.amazonaws.com",
            "redshift-serverless.amazonaws.com",
            "sagemaker.amazonaws.com"
          ]
        },
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "redshift_commands_policy" {
  name = "AmazonRedshiftCommandsAccessPolicy"
  role = aws_iam_role.redshift_commands_access_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid = "S3Access",
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:GetBucketAcl",
          "s3:GetBucketCors",
          "s3:GetEncryptionConfiguration",
          "s3:GetBucketLocation",
          "s3:ListBucket",
          "s3:ListAllMyBuckets",
          "s3:ListMultipartUploadParts",
          "s3:ListBucketMultipartUploads",
          "s3:PutObject",
          "s3:PutBucketAcl",
          "s3:PutBucketCors",
          "s3:DeleteObject",
          "s3:AbortMultipartUpload",
          "s3:CreateBucket"
        ],
        Resource = "arn:aws:s3:::*"
      },
      {
        Sid = "KMSAccess",
        Effect = "Allow",
        Action = [
          "kms:ReEncryptTo",
          "kms:ReEncryptFrom",
          "kms:ListGrants",
          "kms:GetPublicKey",
          "kms:GetParametersForImport",
          "kms:GetKeyPolicy",
          "kms:GenerateDataKeyPair",
          "kms:GenerateDataKey",
          "kms:Encrypt",
          "kms:DescribeKey",
          "kms:Decrypt",
          "kms:CreateAlias"
        ],
        Resource = data.aws_kms_key.master.arn
      },
      {
        Sid = "KMSList",
        Effect = "Allow",
        Action = [
          "kms:ListAliases",
          "kms:List*",
          "kms:Describe*"
        ],
        Resource = "*"
      }
    ]
  })
}
