import "tfplan/v2" as tfplan

authenticated_users_uri = "http://acs.amazonaws.com/groups/global/AuthenticatedUsers"

violating_acls = filter(tfplan.resource_changes or []) as address, rc {
  rc.type is "aws_s3_bucket_acl" and
  (rc.change.actions contains "create" or rc.change.actions contains "update") and

  # safe guard checks
  (rc.change.after contains "access_control_policy") and
  (rc.change.after.access_control_policy contains "grant") and
  (type(rc.change.after.access_control_policy.grant) is list) and

  any rc.change.after.access_control_policy.grant as grant {
    grant contains "grantee" and
    grant.grantee contains "uri" and
    grant.grantee.uri is authenticated_users_uri and
    (grant.permission in ["READ", "WRITE_ACP"])
  }
}
