resource "null_resource" "enable_private_dns" {
  depends_on = [aws_vpc_endpoint.vpce]

  triggers = {
    vpce_id = aws_vpc_endpoint.vpce.id
  }

  provisioner "local-exec" {
    command = "bash enable-private-dns.sh ${aws_vpc_endpoint.vpce.id}"
  }
}
