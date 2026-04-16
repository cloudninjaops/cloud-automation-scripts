import boto3

def assume_role(role_arn, session_name="tfc-tagging-session"):
    
    # Step 1 — uses default creds (Account A / TFC agent)
    sts_client = boto3.client("sts")
    
    response = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name
    )
    
    creds = response["Credentials"]
    
    # Step 2 — new session using Account B temp creds
    session = boto3.Session(
        aws_access_key_id     = creds["AccessKeyId"],
        aws_secret_access_key = creds["SecretAccessKey"],
        aws_session_token     = creds["SessionToken"],
        region_name           = AWS_REGION
    )
    
    return session