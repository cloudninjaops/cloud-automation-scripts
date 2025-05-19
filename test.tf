

use_common_role = try(each.value.use_common_role, false)
#-----
use_common_role = var.use_common_role
common_role_name = var.use_common_role ? "${var.app_name_short}-${var.env_name}-lbd-common-role" : null
#--
use_common_role        = try(local.cloud_components.lambdas.use_common_role, false)
common_role_name       = "${local.app_name_short}-${var.env_name}-lbd-common-role"
lambda_function_names  = keys(try(local.cloud_components.lambdas, {}))


##----

resource "aws_iam_role" "lambda" {
  count = var.use_common_role ? (var.function_ordinal == 1 ? 1 : 0) : 1
  name  = var.use_common_role ? var.common_role_name : "${var.app_name_short}-${var.env_name}-lbdrole-${var.function_ordinal}"
  ...
}

output "iam_role_name" {
  value = var.use_common_role ? aws_iam_role.lambda[0].name : aws_iam_role.lambda[0].name
}

#lambda
role = var.use_common_role ? aws_iam_role.lambda[0].arn : aws_iam_role.lambda[0].arn

resource "aws_lambda_permission" "allow_cross_lambda" {
  count = var.use_common_role ? length(var.lambda_function_names) : 0
  statement_id  = "AllowInvokeFromLambda${count.index}"
  action        = "lambda:InvokeFunction"
  function_name = element(var.lambda_function_names, count.index)
  principal     = "lambda.amazonaws.com"
  source_arn    = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:${element(var.lambda_function_names, count.index)}"
}

#--
lambda_function_names = local.use_common_role ? keys(local.cloud_components.lambdas) : []


#----
#vars 
variable "use_common_role" {
  type    = bool
  default = false
}

variable "common_role_name" {
  type    = string
  default = null
}

variable "lambda_function_names" {
  type    = list(string)
  default = []
}

resource "aws_iam_role" "lambda" {
  count = var.use_common_role ? (var.function_ordinal == 1 ? 1 : 0) : 1

  name = var.use_common_role ? var.common_role_name : (
    var.region == "us-east-1" ?
    join("", [..., var.function_ordinal]) :
    lower(join("-", [..., var.function_ordinal]))
  )

  ...
}

role = var.use_common_role ? aws_iam_role.lambda[0].arn : aws_iam_role.lambda[0].arn

resource "aws_lambda_permission" "cross_lambda_invoke" {
  count = var.use_common_role ? length(var.lambda_function_names) : 0

  statement_id  = "AllowInvokeFromLambda${count.index}"
  action        = "lambda:InvokeFunction"
  function_name = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:${var.app_name_short}-${var.env_name}-${element(var.lambda_function_names, count.index)}"
  principal     = "lambda.amazonaws.com"
}

resource "aws_iam_policy" "common_cross_lambda_invoke" {
  count = var.use_common_role && var.function_ordinal == 1 ? 1 : 0

  name   = "${var.common_role_name}-InvokeOthers"
  path   = var.policy_creation_path
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      for fname in var.lambda_function_names : {
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:${var.app_name_short}-${var.env_name}-${fname}"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "common_cross_lambda_attach" {
  count      = var.use_common_role && var.function_ordinal == 1 ? 1 : 0
  role       = aws_iam_role.lambda[0].name
  policy_arn = aws_iam_policy.common_cross_lambda_invoke[0].arn
}



  function_ordinal = index([
    for fname, fval in try(local.cloud_components.lambdas, {}) :
    fname if fname != "use_common_role"
  ], each.key) + 1


  role = var.use_common_role
  ? (
      var.function_ordinal == 1
        ? aws_iam_role.lambda[0].arn
        : data.aws_iam_role.common[0].arn
    )
  : aws_iam_role.lambda[0].arn



  data "aws_caller_identity" "current" {}

output "terraform_execution_role_info" {
  value = {
    account_id = data.aws_caller_identity.current.account_id
    user_id    = data.aws_caller_identity.current.user_id
    arn        = data.aws_caller_identity.current.arn
  }
}