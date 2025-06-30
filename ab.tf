resource "aws_secretsmanager_secret" "acm_key" {
  name        = "${var.env_type}-${var.app_name}-acm-cert-key"
  description = "Private key for ${var.env_type}-${var.app_name} ACM certificate"
  tags        = var.tags
}

resource "aws_secretsmanager_secret_version" "acm_key_version" {
  secret_id     = aws_secretsmanager_secret.acm_key.id
  secret_string = data.external.get-certificate.result.private_key
}
