import boto3
import paramiko
import time
import subprocess  # Untuk menjalankan perintah curl secara otomatis

# AWS Configuration
AWS_REGION = "us-east-1"  # Ganti dengan region Anda
INSTANCE_TYPE = "t2.micro"  # Instance type EC2
AMI_ID = "ami-0e2c8caa4b6378d8c"  # Ganti dengan AMI ID (Amazon Linux)
KEY_NAME = "jij"  # Ganti dengan nama key pair Anda
SECURITY_GROUP_ID = "sg-05e2501e7afbaf442"  # Ganti dengan ID security group yang sudah ada

# Squid Proxy & Lumina Configuration
LUMINA_USERNAME = "brd-customer-hl_3ed253ee-zone-residential_proxy1"
LUMINA_PASSWORD = "oahn7qt2kt61"
SQUID_CONF = """http_port 3128

acl to_lumina proxy_auth REQUIRED
http_access allow to_lumina

cache deny all
access_log none
cache_log /dev/null

request_header_access Via deny all
request_header_access X-Forwarded-For deny all
request_header_access Cache-Control deny all

cache_peer lumina_residential.example.com parent 443 0 no-query no-digest originserver ssl login={username}:{password}
""".format(username=LUMINA_USERNAME, password=LUMINA_PASSWORD)

CURL_PROXY = "brd.superproxy.io:33335"
CURL_USER = "brd-customer-hl_3ed253ee-zone-residential_proxy1"
CURL_PASS = "oahn7qt2kt61"
CURL_URL = "https://geo.brdtest.com/mygeo.json"

def launch_instance(ec2_client):
    try:
        response = ec2_client.run_instances(
            ImageId=AMI_ID,
            InstanceType=INSTANCE_TYPE,
            KeyName=KEY_NAME,
            MaxCount=1,
            MinCount=1,
            SecurityGroupIds=[SECURITY_GROUP_ID],
        )
        instance = response['Instances'][0]
        instance_id = instance['InstanceId']
        print(f"Instance launched: {instance_id}")
        return instance_id
    except Exception as e:
        print(f"Error launching instance: {e}")
        return None

def get_instance_public_ip(ec2_client, instance_id):
    while True:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        if instance.get('PublicIpAddress'):
            return instance['PublicIpAddress']
        time.sleep(30)

def configure_instance(ip_address):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    private_key_path = "C:/Users/USER/Documents/jij.pem"
    key = paramiko.RSAKey.from_private_key_file(private_key_path)

    try:
        print(f"Waiting for SSH to become ready...")
        time.sleep(60)  # Tunggu 60 detik untuk memastikan instance siap

        print(f"Connecting to {ip_address}...")
        ssh.connect(hostname=ip_address, username="ubuntu", pkey=key, timeout=60)

        # Install Squid Proxy
        commands = [
            "sudo apt-get update -y",
            "sudo apt-get install -y squid",
            f"echo \"{SQUID_CONF}\" | sudo tee /etc/squid/squid.conf",
            "sudo systemctl start squid",
            "sudo systemctl enable squid",
            "sudo systemctl restart squid"
        ]
        for command in commands:
            print(f"Executing: {command}")
            stdin, stdout, stderr = ssh.exec_command(command)
            print(stdout.read().decode(), stderr.read().decode())

        print("Squid Proxy configured successfully.")
    except Exception as e:
        print(f"Error configuring instance: {e}")
    finally:
        ssh.close()

def test_proxy():
    print("Testing proxy with curl...")
    curl_command = [
        "curl",
        "--proxy", CURL_PROXY,
        "--proxy-user", f"{CURL_USER}:{CURL_PASS}",
        "-k", CURL_URL
    ]
    try:
        result = subprocess.run(curl_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print("Curl Test Result:")
            print(result.stdout)
        else:
            print("Curl Test Error:")
            print(result.stderr)
    except Exception as e:
        print(f"Error testing proxy with curl: {e}")

if __name__ == "__main__":
    ec2_client = boto3.client('ec2', region_name=AWS_REGION)

    # Step 1: Launch EC2 Instance
    instance_id = launch_instance(ec2_client)
    if not instance_id:
        exit(1)

    # Step 2: Wait for Public IP
    public_ip = get_instance_public_ip(ec2_client, instance_id)
    print(f"Instance public IP: {public_ip}")

    # Step 3: Configure Instance with Squid Proxy
    configure_instance(public_ip)

    # Step 4: Test Proxy with Curl
    test_proxy()

    print(f"Proxy server is ready at {public_ip}:3128")
