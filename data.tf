# Fetch non-default VPC (first one found)
data "aws_vpc" "selected" {
  filter {
    name   = "isDefault"
    values = ["false"]
  }
}

# Fetch all subnets in the selected VPC
data "aws_subnets" "all_in_vpc" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.selected.id]
  }
}

# Fetch default route table of the selected VPC (used by Gateway endpoints)
data "aws_route_tables" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.selected.id]
  }

  filter {
    name   = "association.main"
    values = ["true"]
  }
}

# (Optional) Caller account ID – useful for logging/debugging
data "aws_caller_identity" "current" {}
