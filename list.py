import boto3
import argparse
import json

def get_session(region):
    session = boto3.Session(region_name=region)
    return session

def get_latest_golden_ami(ec2_client):
    response = ec2_client.describe_images(
        Owners=["self"],
        Filters=[{"Name": "name", "Values": ["golden*"]}
        ]
    )
    images = response.get('Images', [])
    if not images:
        raise Exception("No golden AMI found.")
    images_sorted = sorted(images, key=lambda x: x['CreationDate'], reverse=True)
    latest_image = images_sorted[0]
    return latest_image

def list_ami_sharing(ec2_client, ami_id):
    response = ec2_client.describe_image_attribute(
        ImageId=ami_id,
        Attribute='launchPermission'
    )
    permissions = response.get('LaunchPermissions', [])
    accounts = [perm['UserId'] for perm in permissions if 'UserId' in perm]
    return accounts

def get_kms_key_policy(kms_client, kms_key_id):
    response = kms_client.get_key_policy(
        KeyId=kms_key_id,
        PolicyName='default'
    )
    policy = json.loads(response['Policy'])
    return policy

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', required=True, help="AWS region")
    parser.add_argument('--kms_key_id', required=True, help="KMS Key ID used by AMI snapshots")
    args = parser.parse_args()

    session = get_session(args.region)

    ec2_client = session.client('ec2')
    kms_client = session.client('kms')

    latest_ami = get_latest_golden_ami(ec2_client)
    ami_id = latest_ami['ImageId']
    print(f"Latest Golden AMI ID: {ami_id}")

    shared_accounts = list_ami_sharing(ec2_client, ami_id)
    if shared_accounts:
        print("AMI is shared with the following account IDs:")
        for account in shared_accounts:
            print(f"  - {account}")
    else:
        print("AMI is not shared with any accounts.")

    policy = get_kms_key_policy(kms_client, args.kms_key_id)
    print("Current KMS Key Policy:")
    print(json.dumps(policy, indent=2))

if __name__ == "__main__":
    main()
