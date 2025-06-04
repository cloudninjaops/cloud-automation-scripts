data "aws_sts_caller_identity" "current" {}

resource "aws_iam_role" "kendra_role" {
  name = "kendra-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "kendra.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  inline_policy {
    name = "kendra-inline-policy"

    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect   = "Allow"
          Action   = ["cloudwatch:PutMetricData"]
          Resource = "*"
          Condition = {
            StringEquals = {
              "cloudwatch:namespace" = "AWS/Kendra"
            }
          }
        },
        {
          Effect   = "Allow"
          Action   = ["logs:DescribeLogGroups"]
          Resource = "*"
        },
        {
          Effect   = "Allow"
          Action   = ["logs:CreateLogGroup"]
          Resource = [
            "arn:aws:logs:us-east-1:${data.aws_sts_caller_identity.current.account_id}:log-group:/aws/kendra/*"
          ]
        },
        {
          Effect   = "Allow"
          Action   = [
            "logs:DescribeLogStreams",
            "logs:CreateLogStream",
            "logs:PutLogEvents"
          ]
          Resource = [
            "arn:aws:logs:us-east-1:${data.aws_sts_caller_identity.current.account_id}:log-group:/aws/kendra/*:log-stream:*"
          ]
        },
        {
          Effect = "Allow"
          Action = ["s3:GetObject"]
          Resource = ["arn:aws:s3:::*/"]
        },
        {
          Effect = "Allow"
          Action = [
            "s3:ListBucket",
            "s3:Put*"
          ]
          Resource = ["arn:aws:s3:::*"]
        },
        {
          Sid    = "StmtKMSAccess"
          Effect = "Allow"
          Action = [
            "kms:CreateGrant",
            "kms:DescribeKey",
            "kms:Decrypt"
          ]
          Resource = "*"
        },
        {
          Sid    = "StmtKendraActions"
          Effect = "Allow"
          Action = ["kendra:*"]
          Resource = "*"
        },
        {
          Sid    = "StmtSSOActions"
          Effect = "Allow"
          Action = [
            "sso:AssociateProfile",
            "sso:CreateManagedApplicationInstance",
            "sso:DeleteManagedApplicationInstance",
            "sso:DisassociateProfile",
            "sso:GetManagedApplicationInstance",
            "sso:GetProfile",
            "sso:ListDirectoryAssociations",
            "sso:ListProfileAssociations",
            "sso:ListProfiles"
          ]
          Resource = "*"
        },
        {
          Sid    = "StmtSSODirectory"
          Effect = "Allow"
          Action = [
            "sso-directory:DescribeGroup",
            "sso-directory:DescribeGroups",
            "sso-directory:DescribeUser",
            "sso-directory:DescribeUsers"
          ]
          Resource = "*"
        },
        {
          Sid    = "StmtIdentityStore"
          Effect = "Allow"
          Action = [
            "identitystore:DescribeGroup",
            "identitystore:DescribeUser",
            "identitystore:ListGroups",
            "identitystore:ListUsers"
          ]
          Resource = "*"
        },
        {
          Sid    = "ENITagPolicy"
          Effect = "Allow"
          Action = ["ec2:CreateTags"]
          Resource = "*"
        }
      ]
    })
  }

  tags = {
    Name = "kendra-role"
  }
}
