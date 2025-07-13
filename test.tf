locals {
  ec2_user_data_map = {
    for config in local.ec2_grps_instances :
    config.instance_name => (
      length(try(config.instance_settings.custom_user_data, [])) > 0 ?
      join("\n", [
        for cud_file in config.instance_settings.custom_user_data :
        trimspace(filebase64("${local.app_resources_path}/${replace(cud_file, "userdata/", "")}"))
      ]) :
      null
    )
  }
}


-----
custom_user_data = try(local.ec2_user_data_map[each.value.instance_name], null)