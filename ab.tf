resource "null_resource" "enable_private_dns" {
  triggers = {
    vpce_id = aws_vpc_endpoint.example.id
  }

  provisioner "local-exec" {
    command = <<EOT
echo "Trying to enable private DNS for VPC Endpoint: ${aws_vpc_endpoint.example.id}"

aws ec2 modify-vpc-endpoint \
  --vpc-endpoint-id ${aws_vpc_endpoint.example.id} \
  --private-dns-enabled

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "Warning: Failed to enable Private DNS. It might already be enabled or unsupported for this service or VPC."
else
  echo "Private DNS enabled successfully."
fi
EOT
  }
}
