connection_properties = {
  JDBC_CONNECTION_URL = local.is_serverless ?
    "jdbc:redshift://${aws_redshiftserverless_workgroup.this[0].endpoint[0].address}:${var.redshift_port}/${var.redshift_db_name}" :
    "jdbc:redshift://${aws_redshift_cluster.this[0].endpoint}:${var.redshift_port}/${var.redshift_db_name}"

  USERNAME = var.redshift_admin_username
  PASSWORD = lookup(data.external.get_redshift_password_cyark.result, terraform_data.get_redshift_password.output.account)
}
