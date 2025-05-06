#!/bin/bash

# List of AWS regions
regions=("us-east-1" "us-east-2")

for region in "${regions[@]}"; do
  echo "Checking default VPC in region: $region"

  # Get the default VPC ID
  default_vpc_id=$(aws ec2 describe-vpcs --region "$region" --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text)

  # Check if default VPC exists
  if [ "$default_vpc_id" != "None" ]; then
    echo "Default VPC found: $default_vpc_id"

    # Detach and delete the Internet Gateway if attached to the default VPC
    echo "Detaching and deleting Internet Gateway..."
    igw_id=$(aws ec2 describe-internet-gateways --region "$region" --filters "Name=attachment.vpc-id,Values=$default_vpc_id" --query "InternetGateways[0].InternetGatewayId" --output text)
    if [ "$igw_id" != "None" ]; then
      aws ec2 detach-internet-gateway --region "$region" --internet-gateway-id "$igw_id" --vpc-id "$default_vpc_id"
      aws ec2 delete-internet-gateway --region "$region" --internet-gateway-id "$igw_id"
    fi

    # Delete associated route tables (skip main route table)
    echo "Deleting associated Route Tables..."
    route_table_ids=$(aws ec2 describe-route-tables --region "$region" --filters "Name=vpc-id,Values=$default_vpc_id" --query "RouteTables[?Associations[?Main!=`true`]].RouteTableId" --output text)
    for rt_id in $route_table_ids; do
      aws ec2 delete-route-table --region "$region" --route-table-id "$rt_id"
    done

    # Delete associated subnets
    echo "Deleting associated Subnets..."
    subnet_ids=$(aws ec2 describe-subnets --region "$region" --filters "Name=vpc-id,Values=$default_vpc_id" --query "Subnets[].SubnetId" --output text)
    for subnet_id in $subnet_ids; do
      aws ec2 delete-subnet --region "$region" --subnet-id "$subnet_id"
    done

    # Delete associated security groups (except default security group)
    echo "Deleting associated Security Groups..."
    security_group_ids=$(aws ec2 describe-security-groups --region "$region" --filters "Name=vpc-id,Values=$default_vpc_id" --query "SecurityGroups[?GroupName!='default'].GroupId" --output text)
    for sg_id in $security_group_ids; do
      aws ec2 delete-security-group --region "$region" --group-id "$sg_id"
    done

    #Delete the default VPC
    echo "Deleting default VPC..."
    aws ec2 delete-vpc --region "$region" --vpc-id "$default_vpc_id"
    echo "Default VPC and its resources deleted successfully!"
  else
    echo "No default VPC found in region $region, skipping..."
  fi
done

echo "Script execution completed."
