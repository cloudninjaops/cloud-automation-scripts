#!/bin/bash

# Redirect output to console and log file
exec > >(tee -a cleanup.log) 2>&1

# Validate regions array
if [ -z "${regions+x}" ] || [ ${#regions[@]} -eq 0 ]; then
  echo "Error: regions array is not defined or empty."
  exit 1
fi

# Main loop for each region
for region in "${regions[@]}"; do
  echo "Processing region: $region"

  # Validate default_vpc_id
  if [ -z "$default_vpc_id" ] || [ "$default_vpc_id" = "None" ]; then
    echo "No default VPC found in region $region, skipping..."
    continue
  fi

  # Detach and delete Internet Gateway
  echo "Checking for Internet Gateway in region: $region"
  igw_id=$(aws ec2 describe-internet-gateways --region "$region" --filters "Name=attachment.vpc-id,Values=$default_vpc_id" --query "InternetGateways[0].InternetGatewayId" --output text 2>/dev/null) || {
    echo "Error querying Internet Gateway in region $region."
    continue
  }
  if [ "$igw_id" != "None" ] && [ -n "$igw_id" ]; then
    echo "Found Internet Gateway $igw_id"
    echo "Detaching Internet Gateway $igw_id..."
    aws ec2 detach-internet-gateway --region "$region" --internet-gateway-id "$igw_id" --vpc-id "$default_vpc_id" 2>/dev/null || {
      echo "Failed to detach Internet Gateway $igw_id in region $region."
      continue
    }
    echo "Deleting Internet Gateway $igw_id..."
    aws ec2 delete-internet-gateway --region "$region" --internet-gateway-id "$igw_id" 2>/dev/null || {
      echo "Failed to delete Internet Gateway $igw_id in region $region."
      continue
    }
  else
    echo "No Internet Gateway found in region $region."
  fi

  # Delete associated Route Tables (skip main route table)
  echo "Checking for non-main route tables in region: $region"
  route_table_ids=$(aws ec2 describe-route-tables --region "$region" --filters "Name=vpc-id,Values=$default_vpc_id" --query "RouteTables[?Associations[?Main!=true]].RouteTableId" --output text 2>/dev/null) || {
    echo "Error querying route tables in region $region."
    continue
  }
  if [ -z "$route_table_ids" ]; then
    echo "No non-main route tables found in region $region."
  else
    for rt_id in $route_table_ids; do
      echo "Found route table $rt_id"
      echo "Deleting route table $rt_id..."
      aws ec2 delete-route-table --region "$region" --route-table-id "$rt_id" 2>/dev/null || {
        echo "Failed to delete route table $rt_id in region $region. Dependencies may exist."
        continue
      }
    done
  fi

  # Delete associated Subnets
  echo "Checking for subnets in region: $region"
  subnet_ids=$(aws ec2 describe-subnets --region "$region" --filters "Name=vpc-id,Values=$default_vpc_id" --query "Subnets[].SubnetId" --output text 2>/dev/null) || {
    echo "Error querying subnets in region $region."
    continue
  }
  if [ -z "$subnet_ids" ]; then
    echo "No subnets found in region $region."
  else
    for subnet_id in $subnet_ids; do
      echo "Found subnet $subnet_id"
      echo "Deleting subnet $subnet_id..."
      aws ec2 delete-subnet --region "$region" --subnet-id "$subnet_id" 2>/dev/null || {
        echo "Failed to delete subnet $subnet_id in region $region. Resources may still exist."
        continue
      }
    done
  fi

  # Delete associated Security Groups (excluding default security group)
  echo "Checking for non-default security groups in region: $region"
  security_group_ids=$(aws ec2 describe-security-groups --region "$region" --filters "Name=vpc-id,Values=$default_vpc_id" --query "SecurityGroups[?GroupName!='default'].GroupId" --output text 2>/dev/null) || {
    echo "Error querying security groups in region $region."
    continue
  }
  if [ -z "$security_group_ids" ]; then
    echo "No non-default security groups found in region $region."
  else
    for sg_id in $security_group_ids; do
      echo "Found security group $sg_id"
      echo "Deleting security group $sg_id..."
      aws ec2 delete-security-group --region "$region" --group-id "$sg_id" 2>/dev/null || {
        echo "Failed to delete security group $sg_id in region $region. Dependencies may exist."
        continue
      }
    done
  fi

  # Delete the default VPC
  echo "Checking for default VPC in region: $region"
  echo "Deleting default VPC $default_vpc_id..."
  aws ec2 delete-vpc --region "$region" --vpc-id "$default_vpc_id" 2>/dev/null || {
    echo "Failed to delete default VPC $default_vpc_id in region $region. Dependencies may exist."
    continue
  }
  echo "Default VPC and its resources deleted successfully in region $region!"
done

echo "Cleanup process completed. Check cleanup.log for details."