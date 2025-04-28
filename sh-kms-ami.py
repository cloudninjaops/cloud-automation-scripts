import boto3
import argparse
import json

def get_session(region):
    session = boto3.Session(region_name=region)
    return session

def print_current_identity(session):
    sts_client = session.client('sts')
    identity = sts_client.get_caller_identity()
    print("Current AWS Identity:")
    print(f"  Account ID : {identity['Account']}")
    print(f"  Role/User ARN : {identity['Arn']}")

def get_latest_golden_ami(ec2_client):
    response = ec2_client.describe_images(
        Owners=["self"],
        Filters=[{"Name": "name", "Values": ["golden*"]}]
    )
    images = response.get('Images', [])
    if not images:
        raise Exception("No golden AMI found.")
    images_sorted = sorted(images, key=lambda x: x['CreationDate'], reverse=True)
    latest_image = images_sorted[0]
    return latest_image

def share_ami_and_snapshots(ec2_client, image, target_account_id):
    ami_id = image['ImageId']
    ec2_client.modify_image_attribute(
        ImageId=ami_id,
        LaunchPermission={'Add': [{'UserId': target_account_id}]}
    )
    for block in image.get('BlockDeviceMappings', []):
        if 'Ebs' in block:
            snapshot_id = block['Ebs']['SnapshotId']
            ec2_client.modify_snapshot_attribute(
                SnapshotId=snapshot_id,
                Attribute='createVolumePermission',
                OperationType='add',
                UserIds=[target_account_id]
            )

def update_kms_key_policy(kms_client, kms_key_id, target_role_arn):
    response = kms_client.get_key_policy(
        KeyId=kms_key_id,
        PolicyName="default"
    )
    policy = json.loads(response['Policy'])
    new_statement = {
        "Sid": "AllowUseOfKeyForNewAccount",
        "Effect": "Allow",
        "Principal": {
            "AWS": target_role_arn
        },
        "Action": [
            "kms:Decrypt",
            "kms:Encrypt",
            "kms:GenerateDataKey*",
            "kms:CreateGrant"
        ],
        "Resource": "*"
    }
    if not any(stmt.get("Sid") == "AllowUseOfKeyForNewAccount" for stmt in policy.get("Statement", [])):
        policy["Statement"].append(new_statement)
    kms_client.put_key_policy(
        KeyId=kms_key_id,
        Policy=json.dumps(policy),
        PolicyName="default"
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', required=True, help="AWS region")
    parser.add_argument('--target_account_id', required=True, help="Target AWS account ID")
    parser.add_argument('--target_role_name', required=True, help="Role name in the new account")
    parser.add_argument('--kms_key_id', required=True, help="KMS Key ID used by AMI snapshots")
    args = parser.parse_args()

    session = get_session(args.region)

    print_current_identity(session)

    ec2_client = session.client('ec2')
    kms_client = session.client('kms')

    latest_ami = get_latest_golden_ami(ec2_client)
    share_ami_and_snapshots(ec2_client, latest_ami, args.target_account_id)

    target_role_arn = f"arn:aws:iam::{args.target_account_id}:role/{args.target_role_name}"
    update_kms_key_policy(kms_client, args.kms_key_id, target_role_arn)

    print("AMI sharing and KMS policy update completed.")

if __name__ == "__main__":
    main()
