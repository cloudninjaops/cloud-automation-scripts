resource "null_resource" "enable_private_dns" {
  depends_on = [ aws_vpc_endpoint.vpce ]
  triggers = {
    vpce_id = aws_vpc_endpoint.vpce.id
  }

  provisioner "local-exec" {
    command = <<EOT
echo "Trying to enable private DNS for VPC Endpoint: ${aws_vpc_endpoint.vpce.id}"
echo "Waiting up to 10 minutes for the resource to become available..."

MAX_WAIT=600
SLEEP_INTERVAL=10
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
  STATUS=$(aws ec2 describe-vpc-endpoints \
    --vpc-endpoint-ids ${aws_vpc_endpoint.vpce.id} \
    --query "VpcEndpoints[0].State" \
    --output text 2>/dev/null)

  echo "Status: $STATUS (elapsed: ${ELAPSED}s)"
  
  if [ "$STATUS" == "available" ]; then
    echo "VPC Endpoint is available. Enabling Private DNS..."
    aws ec2 modify-vpc-endpoint \
      --vpc-endpoint-id ${aws_vpc_endpoint.vpce.id} \
      --private-dns-enabled \
    && echo "✅ Private DNS enabled successfully." \
    || echo "⚠️  Warning: Failed to enable Private DNS. It may already be enabled or not supported."

    exit 0
  fi

  sleep $SLEEP_INTERVAL
  ELAPSED=$((ELAPSED + SLEEP_INTERVAL))
done

echo "⚠️  Timeout: VPC Endpoint did not reach 'available' state in 10 minutes."
exit 0
EOT
  }
}
