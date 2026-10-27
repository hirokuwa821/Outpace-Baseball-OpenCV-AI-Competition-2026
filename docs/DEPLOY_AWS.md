# AWS Deployment Guide: Outpace Baseball (EC2 + Docker)

This guide provides end-to-end instructions for deploying the **Outpace Baseball** application onto **Amazon Web Services (AWS)** using an **Amazon EC2** instance running Docker, integrated with **Amazon S3** (for video storage) and **Amazon Bedrock** (for AI coaching with Amazon Nova 2 Lite) through an **IAM Instance Role** (no long-term access keys stored on instances).

---

## 1. Architecture Overview

```
                                      +---------------------------------------------+
                                      | Amazon EC2 (Ubuntu 24.04 LTS / t3.large)    |
                                      |                                             |
[User / Judge Browser] -- (HTTP 80) ->|   Docker Container (outpace-app)           |
                                      |   * Streamlit UI (Port 8501)                |
                                      |   * YOLO11n-pose (CPU Inference)            |
                                      |   * Aerodynamics & Biomechanics Engine     |
                                      |   * boto3 SDK (Uses IAM Instance Role)      |
                                      +----------------------+----------------------+
                                                             |
                              +------------------------------+------------------------------+
                              |                                                             |
                              v                                                             v
               +------------------------------+                              +------------------------------+
               |        Amazon S3             |                              |    Amazon Bedrock Runtime    |
               |  s3://YOUR_BUCKET_NAME/      |                              |  Model: amazon.nova-2-lite   |
               |  videos/{video_name}.mp4     |                              |  (System Inference Profiles) |
               +------------------------------+                              +------------------------------+
```

- **Ephemeral Container Design**: The application runs inside Docker. Analysis is performed on-instance. Newly uploaded videos are stored locally and copied to S3 (`videos/` prefix).
- **IAM Instance Role**: `boto3` automatically retrieves temporary credentials via IMDSv2. No secrets or keys exist in the repository or container image.

---

## 2. Prerequisites

1. **AWS CLI v2** installed and configured (`aws configure`).
2. AWS account permissions to manage EC2, IAM, S3, and Bedrock.
3. Model access enabled for **Amazon Nova 2 Lite** in Amazon Bedrock console:
   - Navigate to AWS Console -> **Amazon Bedrock** -> **Model access**.
   - Click **Modify model access**, check **Amazon: Nova 2 Lite**, and click **Save changes**.

Set your configuration variables in your local shell before running the commands below:

```bash
export AWS_REGION="YOUR_REGION"                # e.g., us-east-1 or ap-northeast-1
export BUCKET_NAME="YOUR_BUCKET_NAME"          # Must be globally unique, e.g., outpace-baseball-data-12345
export ROLE_NAME="OutpaceBaseballEC2Role"
export POLICY_NAME="OutpaceBaseballPolicy"
export PROFILE_NAME="OutpaceBaseballInstanceProfile"
export SG_NAME="outpace-baseball-sg"
```

---

## 3. Step-by-Step AWS CLI Deployment

### Step 3.1: Create and Secure S3 Bucket

```bash
# 1. Create S3 Bucket (us-east-1 does not accept LocationConstraint)
if [ "$AWS_REGION" = "us-east-1" ]; then
  aws s3api create-bucket \
    --bucket "$BUCKET_NAME" \
    --region "$AWS_REGION"
else
  aws s3api create-bucket \
    --bucket "$BUCKET_NAME" \
    --region "$AWS_REGION" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION"
fi

# 2. Block all public access
aws s3api put-public-access-block \
  --bucket "$BUCKET_NAME" \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# 3. Enable default server-side encryption (SSE-S3)
aws s3api put-bucket-encryption \
  --bucket "$BUCKET_NAME" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

---

### Step 3.2: Create IAM Role and Instance Profile

```bash
# 1. Prepare IAM policy file with your bucket name
sed -i "s/YOUR_BUCKET_NAME/$BUCKET_NAME/g" deploy/iam-policy.json

# 2. Create IAM Role with EC2 trust policy
aws iam create-role \
  --role-name "$ROLE_NAME" \
  --assume-role-policy-document file://deploy/ec2-trust-policy.json

# 3. Attach application permissions policy to the role
aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "$POLICY_NAME" \
  --policy-document file://deploy/iam-policy.json

# 4. Create IAM Instance Profile and associate role
aws iam create-instance-profile \
  --instance-profile-name "$PROFILE_NAME"

aws iam add-role-to-instance-profile \
  --instance-profile-name "$PROFILE_NAME" \
  --role-name "$ROLE_NAME"

# Wait 10 seconds for IAM instance profile propagation
sleep 10
```

---

### Step 3.3: Create Security Group

```bash
# 1. Retrieve Default VPC ID
VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query "Vpcs[0].VpcId" \
  --output text \
  --region "$AWS_REGION")

# 2. Create Security Group
SG_ID=$(aws ec2 create-security-group \
  --group-name "$SG_NAME" \
  --description "Security group for Outpace Baseball web app" \
  --vpc-id "$VPC_ID" \
  --query "GroupId" \
  --output text \
  --region "$AWS_REGION")

# 3. Allow inbound HTTP traffic on port 80
# Note: For production, restrict 0.0.0.0/0 to your trusted CIDR / IP range (e.g., YOUR_IP/32)
aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0 \
  --region "$AWS_REGION"
```

---

### Step 3.4: Launch EC2 Instance with Cloud-Init User Data

```bash
# 1. Prepare user data script with your bucket name and region
sed -i "s/YOUR_BUCKET_NAME/$BUCKET_NAME/g" deploy/ec2_user_data.sh
sed -i "s/YOUR_REGION/$AWS_REGION/g" deploy/ec2_user_data.sh

# 2. Query the latest official Ubuntu 24.04 LTS AMI (Noble)
UBUNTU_AMI=$(aws ssm get-parameter \
  --name "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id" \
  --query "Parameter.Value" \
  --output text \
  --region "$AWS_REGION")

# 3. Launch t3.large instance (30 GB gp3 root disk, IMDSv2 enforced)
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$UBUNTU_AMI" \
  --instance-type t3.large \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile Name="$PROFILE_NAME" \
  --user-data file://deploy/ec2_user_data.sh \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
  --metadata-options "HttpTokens=required,HttpEndpoint=enabled" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=OutpaceBaseballApp}]' \
  --query "Instances[0].InstanceId" \
  --output text \
  --region "$AWS_REGION")

echo "Launched EC2 instance: $INSTANCE_ID"
```

---

### Step 3.5: Locate Public DNS and Verification

```bash
# Wait for instance to enter running state
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"

# Get Public DNS and IP
PUBLIC_DNS=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query "Reservations[0].Instances[0].PublicDnsName" \
  --output text \
  --region "$AWS_REGION")

PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query "Reservations[0].Instances[0].PublicIpAddress" \
  --output text \
  --region "$AWS_REGION")

echo "=================================================="
echo "Outpace Baseball Application URL:"
echo "http://${PUBLIC_DNS}"
echo "or http://${PUBLIC_IP}"
echo "=================================================="
```

> **Note on Initial Boot Time**: The cloud-init script installs Docker and builds the Docker container image with CPU PyTorch upon first launch. This typically takes 3 to 5 minutes. You can monitor progress on the instance via:
> ```bash
> tail -f /var/log/cloud-init-output.log
> ```


---

## 4. How to Verify the Deployment

1. **Health Check Endpoint**:
   ```bash
   curl -f "http://${PUBLIC_DNS}/_stcore/health"
   # Expected response: ok (HTTP 200)
   ```
2. **Access Web Interface**:
   Open `http://${PUBLIC_DNS}` in a web browser. Verify the pitch comparison, 3D strike zone, and ball trajectory plots render correctly.
3. **Test Video Upload & S3 Sync**:
   Upload a sample pitch (`videos/pitch_102_1.mp4`). Verify the green local save notification and blue info notification appear:
   `Uploaded to S3: s3://YOUR_BUCKET_NAME/videos/pitch_102_1.mp4`
   Check S3 via CLI:
   ```bash
   aws s3 ls "s3://${BUCKET_NAME}/videos/"
   ```
4. **Test AI Coaching (Amazon Bedrock Nova 2 Lite)**:
   Navigate to the **AI Pitching Coach** tab, type a question (e.g. *"How can I improve my extension?"*), and verify that Amazon Bedrock returns a personalized coaching response.

---

## 5. Teardown Instructions

To avoid ongoing AWS charges after evaluation:

```bash
# 1. Terminate EC2 instance
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"

# 2. Delete Security Group
aws ec2 delete-security-group --group-id "$SG_ID" --region "$AWS_REGION"

# 3. Clean up IAM instance profile and role
aws iam remove-role-from-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME"
aws iam delete-instance-profile --instance-profile-name "$PROFILE_NAME"
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME"
aws iam delete-role --role-name "$ROLE_NAME"

# 4. Empty and delete S3 bucket
aws s3 rm "s3://${BUCKET_NAME}" --recursive
aws s3 rb "s3://${BUCKET_NAME}"

echo "All AWS resources successfully torn down."
```

### Estimated Cost Note
- **EC2 `t3.large`**: ~\$0.0832/hour (~\$2.00/day).
- **EBS 30 GB gp3**: ~\$0.08/GB-month (~\$2.40/month, prorated to hours used).
- **Amazon S3**: Standard tier ~\$0.023/GB-month (pennies for test videos).
- **Amazon Bedrock (Nova 2 Lite)**: On-demand token pricing (\$0.06 per 1M input tokens, \$0.24 per 1M output tokens).

---

## 6. Local Run, Tests, and Smoke Test (Linux / macOS / Windows)

### 6.1 Local Setup on Linux / macOS

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Upgrade pip and install CPU PyTorch first
pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 3. Install project dependencies
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# 4. (Optional) Configure environment variables for AWS
export AWS_S3_BUCKET_NAME="YOUR_BUCKET_NAME"
export AWS_DEFAULT_REGION="YOUR_REGION"

# 5. Run Streamlit application
streamlit run src/app.py
```

### 6.2 Running the Full Unit Test Suite

```bash
python -m unittest discover tests
```
*Expected Result*:
```text
Ran 22 tests in ~1.1s
OK
```

### 6.3 Standalone Smoke Test

Execute the physics analysis script against sample data:

```bash
python src/pitch_speed_v23_auto_distance.py
```
*Expected Output for pitch_102_1*:
```text
動画: pitch_102_1
  投手: 左投
  AI取得座標: プレートY=1048.9, 踏み出し足Y=855.7, ネットY=380.0
  エクステンション: 1.14 m   投球距離: 17.30 m
  飛行時間: 0.6343 s   初速推定: 102.73 km/h
```

