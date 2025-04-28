import boto3
import argparse

def assume_role(account_id, role_name):
    sts_client = boto3.client('sts')
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    assumed_role = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName="SharedSvcSession"
    )
    credentials = assumed_role['Credentials']
    return credentials

def get_latest_golden_ami(ec2_client):
    images = ec2_client.describe_images(
        Filters=[{'Name': 'name', 'Values': ['golden*']}],
        Owners=['self']
    )['Images']
    latest_image = sorted(images, key=lambda x: x['CreationDate'], reverse=True)[0]
    return latest_image

def update_ami_and_snapshots(ec2_client, image_id, new_account_id):
    # Update AMI Launch Permissions
    ec2_client.modify_image_attribute(
        ImageId=image_id,
        LaunchPermission={'Add': [{'UserId': new_account_id}]}
    )

    # Update associated snapshot permissions
    image = ec2_client.describe_images(ImageIds=[image_id])['Images'][0]
    for block_device in image.get('BlockDeviceMappings', []):
        if 'Ebs' in block_device:
            snapshot_id = block_device['Ebs']['SnapshotId']
            ec2_client.modify_snapshot_attribute(
                SnapshotId=snapshot_id,
                Attribute='createVolumePermission',
                OperationType='add',
                UserIds=[new_account_id]
            )

def update_kms_key_policy(kms_client, key_id, new_account_arn):
    policy = kms_client.get_key_policy(KeyId=key_id, PolicyName='default')['Policy']
    
    import json
    policy_json = json.loads(policy)

    # Add new statement
    policy_json['Statement'].append({
        "Sid": "AllowUseOfKeyForNewAccount",
        "Effect": "Allow",
        "Principal": {"AWS": new_account_arn},
        "Action": [
            "kms:Decrypt",
            "kms:Encrypt",
            "kms:GenerateDataKey*",
            "kms:CreateGrant"
        ],
        "Resource": "*"
    })

    kms_client.put_key_policy(
        KeyId=key_id,
        Policy=json.dumps(policy_json),
        PolicyName='default'
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--new_account_id', required=True)
    parser.add_argument('--new_account_role_name', required=True)
    parser.add_argument('--region', required=True)
    args = parser.parse_args()

    # 1. Assume role into Shared SVC
    shared_svc_credentials = assume_role("<shared_svc_account_id>", "<terraform_execution_role>")
    
    # Create boto3 clients using assumed credentials
    ec2 = boto3.client('ec2',
        aws_access_key_id=shared_svc_credentials['AccessKeyId'],
        aws_secret_access_key=shared_svc_credentials['SecretAccessKey'],
        aws_session_token=shared_svc_credentials['SessionToken'],
        region_name=args.region
    )
    
    kms = boto3.client('kms',
        aws_access_key_id=shared_svc_credentials['AccessKeyId'],
        aws_secret_access_key=shared_svc_credentials['SecretAccessKey'],
        aws_session_token=shared_svc_credentials['SessionToken'],
        region_name=args.region
    )

    # 2. Find latest golden AMI
    latest_ami = get_latest_golden_ami(ec2)

    # 3. Update AMI + Snapshot permissions
    update_ami_and_snapshots(ec2, latest_ami['ImageId'], args.new_account_id)

    # 4. Update KMS Policy
    key_id = "<packer_kms_key_id>"
    new_account_role_arn = f"arn:aws:iam::{args.new_account_id}:role/{args.new_account_role_name}"
    update_kms_key_policy(kms, key_id, new_account_role_arn)

    print("✅ Successfully updated AMI and KMS permissions for new account:", args.new_account_id)

if __name__ == "__main__":
    main()
