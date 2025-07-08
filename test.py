def ensure_policy_path_exists(session_tkn, full_dn, base_dn="\\VED\\Policy\\Certs"):
    """
    Ensures that all folders in the policy DN path exist in Venafi.
    Creates any missing intermediate folders using /Config/Create API.

    Args:
        session_tkn: The Venafi bearer tkn.
        full_dn: Full certificate DN path (e.g., \\VED\\Policy\\Certs\\SDK\\AWS\\dev\\account123).
        base_dn: The base DN from which recursive creation is allowed.
    """
    # import urllib.parse

    # Normalize path parts
    dn_parts = full_dn.strip("\\").split("\\")
    base_parts = base_dn.strip("\\").split("\\")

    if dn_parts[:len(base_parts)] != base_parts:
        raise Exception(f"DN must start with base path {base_dn}")

    _headers = {"Authorization": f"Bearer {session_tkn}"}
    _config_validate_url = urllib.parse.urljoin(_base_url, "Config/IsValid")
    _config_create_url = urllib.parse.urljoin(_base_url, "Config/Create")

    current_dn = ""
    for part in dn_parts:
        current_dn = f"{current_dn}\\{part}" if current_dn else f"\\{part}"

        # Validate
        _data = {"ObjectDN": current_dn}
        _resp = _call_api(_config_validate_url, _headers=_headers, _data=_data, _method="POST")

        if not _resp.get("Valid", False):
            # Create missing folder
            _create_payload = {
                "ObjectDN": current_dn,
                "Class": "Policy"
            }
            _create_resp = _call_api(_config_create_url, _headers=_headers, _data=_create_payload, _method="POST")

            if "Error" in _create_resp:
                raise Exception(f"Failed to create policy folder: {current_dn} — {json.dumps(_create_resp)}")
