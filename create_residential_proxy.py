import boto3
import paramiko
import time

# AWS Configuration
AWS_REGION = "us-east-1"
INSTANCE_TYPE = "t2.micro"
AMI_ID = "ami-0e2c8caa4b6378d8c"
KEY_NAME = "a"
SECURITY_GROUP = "squid-proxy-sg"

LUMINA_USERNAME = "brd-customer-hl_3ed253ee-zone-residential_proxy1"
LUMINA_PASSWORD = "oahn7qt2kt61"
PRIVATE_KEY_PATH = "C:/Users/USER/Documents/a (5).pem"

SQUID_CONF = f"""
http_port 3128

acl to_lumina proxy_auth REQUIRED
http_access allow to_lumina

cache deny all
access_log none
cache_log /dev/null

request_header_access Via deny all
request_header_access X-Forwarded-For deny all
request_header_access Cache-Control deny all

cache_peer lumina_residential.example.com parent 443 0 no-query no-digest originserver ssl login={LUMINA_USERNAME}:{LUMINA_PASSWORD}
"""

def wait_for_instance_ready(ec2_client, instance_id):
    """Wait until the instance is in the running state."""
    print("Waiting for instance to be ready...")
    while True:
        try:
            response = ec2_client.describe_instance_status(InstanceIds=[instance_id])
            statuses = response['InstanceStatuses']
            if len(statuses) > 0:
                state = statuses[0]['InstanceState']['Name']
                if state == 'running':
                    print("Instance is running.")
                    return True
        except Exception as e:
            print(f"Error checking instance status: {e}")
        time.sleep(10)

def get_instance_public_ip(ec2_client, instance_id):
    """Get the public IP address of the instance."""
    print("Getting instance public IP...")
    retries = 10
    for attempt in range(retries):
        try:
            response = ec2_client.describe_instances(InstanceIds=[instance_id])
            instance = response['Reservations'][0]['Instances'][0]
            if instance.get('PublicIpAddress'):
                return instance['PublicIpAddress']
        except Exception as e:
            print(f"Error fetching public IP (attempt {attempt + 1}/{retries}): {e}")
        time.sleep(10)
    raise Exception("Failed to get public IP address.")

def configure_instance(ip_address):
    """Configure the EC2 instance with Squid Proxy."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        key = paramiko.RSAKey.from_private_key_file(PRIVATE_KEY_PATH)
        print(f"Connecting to {ip_address}...")
        ssh.connect(hostname=ip_address, username="ec2-user", pkey=key, timeout=60)

        commands = [
            "sudo yum update -y",
            "sudo yum install -y squid",
            f"echo \"{SQUID_CONF}\" | sudo tee /etc/squid/squid.conf",
            "sudo systemctl start squid",
            "sudo systemctl enable squid"
        ]
        for command in commands:
            print(f"Executing: {command}")
            stdin, stdout, stderr = ssh.exec_command(command)
            print(stdout.read().decode(), stderr.read().decode())

        print("Squid Proxy configured successfully.")
    except paramiko.ssh_exception.SSHException as e:
        print(f"SSH Error: {e}")
    except Exception as e:
        print(f"Error configuring instance: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    ec2_client = boto3.client('ec2', region_name=AWS_REGION)

    # Step 1: Create Security Group
    security_group_id = create_security_group(ec2_client)
    if not security_group_id:
        exit(1)

    # Step 2: Launch EC2 Instance
    instance_id = launch_instance(ec2_client, security_group_id)
    if not instance_id:
        exit(1)

    # Step 3: Wait for Instance Ready
    if not wait_for_instance_ready(ec2_client, instance_id):
        print("Instance not ready. Exiting.")
        exit(1)

    # Step 4: Get Public IP
    public_ip = get_instance_public_ip(ec2_client, instance_id)
    print(f"Instance public IP: {public_ip}")

    # Step 5: Configure Instance with Squid Proxy
    configure_instance(public_ip)

    print(f"Proxy server is ready at {public_ip}:3128")
