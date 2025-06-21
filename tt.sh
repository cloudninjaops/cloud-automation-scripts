availability_zones = (
  can(each.value.multi_az) && each.value.multi_az
  ? local.local_availability_zones
  : contains(["sbx", "dev", "dvs", "pfn", "pfp"], var.env_type)
    ? [local.local_availability_zones[0]]
    : local.local_availability_zones
)