# HandsOff Installation Guide

Hello! Welcome to HandsOff. You'll be helping a user set up a remote Android device they can control through MCP. This involves spinning up an EC2 instance with ReDroid (containerized Android) and connecting it back via Tailscale.

This guide is concise by design — you're capable, so use your judgement to fill in gaps.

---

## Step 0: Preflight Checks

Before anything else, verify the user's local machine has the required tools. **Do not proceed to Step 1 until both are satisfied.**

### Tailscale

Check that Tailscale is installed and authenticated:

```bash
tailscale status
```

If missing or not logged in, tell the user to install and authenticate Tailscale on this machine. Point them to https://tailscale.com/download — do not walk them through it.

### AWS CLI

Check that the AWS CLI is installed and authenticated:

```bash
aws sts get-caller-identity
```

If missing or not authenticated, tell the user to install the AWS CLI and run `aws configure` (or `aws sso login`). Point them to https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html and help them through the process.

**Gate: Both `tailscale status` and `aws sts get-caller-identity` must succeed before continuing.**

---

## Step 1: Choose a Region

Tell the user you're ready to provision a `t4g.medium` ARM64 instance. Ask them where they live so you can pick the nearest one.

---

## Step 2: Provision the EC2 Instance

All AWS CLI commands in this step use the chosen region (`--region <region>`).

### 2a. Create an SSH key pair

```bash
aws ec2 create-key-pair \
  --key-name handsoff-key \
  --key-type ed25519 \
  --query 'KeyMaterial' \
  --output text \
  --region <region> > ~/.ssh/handsoff-key.pem

chmod 600 ~/.ssh/handsoff-key.pem
```

### 2b. Create a security group

```bash
aws ec2 create-security-group \
  --group-name handsoff-sg \
  --description "HandsOff instance" \
  --region <region>

aws ec2 authorize-security-group-ingress \
  --group-name handsoff-sg \
  --protocol tcp \
  --port 22 \
  --cidr 0.0.0.0/0 \
  --region <region>
```

Only SSH is needed publicly. All other access goes through Tailscale.

### 2c. Find the latest Ubuntu 24.04 ARM64 AMI

```bash
aws ec2 describe-images \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd*/ubuntu-*-24.04*-arm64-server-*" "Name=architecture,Values=arm64" \
  --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
  --output text \
  --region <region>
```

### 2d. Launch the instance

```bash
aws ec2 run-instances \
  --image-id <ami-id> \
  --instance-type t4g.medium \
  --key-name handsoff-key \
  --security-groups handsoff-sg \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":32}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=handsoff}]' \
  --region <region>
```

32GB root volume is recommended for Android images.

### 2e. Wait and get the public IP

```bash
aws ec2 wait instance-running --instance-ids <instance-id> --region <region>

aws ec2 describe-instances \
  --instance-ids <instance-id> \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text \
  --region <region>
```

### 2f. SSH in

Wait ~30 seconds for sshd to start, then:

```bash
ssh -i ~/.ssh/handsoff-key.pem -o StrictHostKeyChecking=no ubuntu@<public-ip>
```

---

## Step 3: Set Up the EC2 Instance

Run these commands over SSH on the instance.

### 3a. Install dependencies

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl lzip python3-pip linux-modules-extra-$(uname -r)

# Add Docker's official repo (docker-compose-plugin isn't in Ubuntu's default repos)
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo pip3 install requests tqdm --break-system-packages
```

### 3b. Load kernel modules

```bash
sudo modprobe binder_linux devices=binder,hwbinder,vndbinder
sudo modprobe ashmem_linux 2>/dev/null || true  # built-in on newer kernels
```

### 3c. Start Docker

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
```

### 3d. Mount binderfs

```bash
sudo mkdir -p /dev/binderfs
sudo mount -t binder binder /dev/binderfs
```

### 3e. Persist across reboots

```bash
echo 'binder_linux' | sudo tee /etc/modules-load.d/redroid.conf
echo 'options binder_linux devices=binder,hwbinder,vndbinder' | sudo tee /etc/modprobe.d/redroid.conf
echo 'binder /dev/binderfs binder nofail 0 0' | sudo tee -a /etc/fstab
```

---

## Step 4: Deploy HandsOff

Still on the EC2 instance:

```bash
mkdir -p ~/handsoff && cd ~/handsoff
curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/altalt-org/HandsOff/refs/heads/main/docker-compose.yml
sudo docker compose up -d
```

Use `sudo docker compose` since the group change from Step 3c requires a re-login to take effect.

Verify all three containers are running:

```bash
sudo docker compose ps
```

You should see `redroid`, `server`, and `scrcpy-web` all up. The redroid container may take 30-60 seconds or longer to fully boot.

---

## Step 5: Set Up Tailscale on the Instance

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

**Important:** `tailscale up` blocks until the user authorizes the machine in their browser. Run it in the background and capture the auth URL:

```bash
nohup sudo tailscale up > /tmp/ts-out.log 2>&1 &
sleep 5
cat /tmp/ts-out.log
```

This will print an auth URL. **Give this URL to the user** and ask them to open it in their browser to authorize the machine. Wait for them to confirm.

Once authenticated, get the Tailscale IP:

```bash
tailscale ip -4
```

Note this IP — all services are now accessible at:

- `http://<tailscale-ip>:8000` — HandsOff MCP server
- `http://<tailscale-ip>:8080` — scrcpy-web (device screen)

---

## Step 6: Configure MCP and Finish

### 6a. Set up global MCP config

Configure MCP on the user's **local machine** (not the EC2 instance) so the agent harness can reach the HandsOff server.

Detect which harness you're running in and add the MCP server config.

For example, if you are running on claude code, consult claude-code-guide for guidance.

Merge with existing config if present — don't overwrite.

### 6b. Open the device viewer

Open `http://<tailscale-ip>:8080` in the user's browser.

Tell the user:

- Select **H264 Converter** from the decoder options for best performance
- They can watch the Android device in real-time here

### 6c. Wrap up

Tell the user:

- HandsOff is deployed and accessible via Tailscale
- The MCP server is configured — **start a new session** to pick up the new MCP config
- In the new session, the agent will have access to Android device control tools (tap, swipe, type, screenshot, app install, etc.)
