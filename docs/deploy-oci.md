# Deploying Portfolio Manager on Oracle Cloud Infrastructure

This guide covers deploying Portfolio Manager to OCI Always Free tier at `https://finance.eduardomotta.dev` using Docker, Postgres, and OCI Vault for secrets management.

## Prerequisites

- OCI account with Always Free tier access
- Domain name configured (finance.eduardomotta.dev)
- Google Cloud Console project with OAuth credentials
- (Optional) Cumbuca Open Finance OAuth credentials

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    OCI Always Free VM                    │
│                   (Ampere A1 or AMD)                     │
│                                                         │
│  ┌─────────┐     ┌─────────┐     ┌─────────────────┐   │
│  │  Caddy  │────▶│   App   │────▶│    Postgres     │   │
│  │ :80/443 │     │  :8000  │     │     :5432       │   │
│  └─────────┘     └─────────┘     └─────────────────┘   │
│       │               │                   │             │
│       │               ▼                   ▼             │
│       │          OCI Vault           postgres_data      │
│       │          (secrets)           (volume)           │
└───────│─────────────────────────────────────────────────┘
        │                        ▲
        ▼                        │ docker pull
   Internet (:443)               │
                          ┌──────┴──────┐
                          │    GHCR     │
                          │ (pre-built  │
                          │   images)   │
                          └─────────────┘
```

## Deployment Flow

The deployment process has been optimized for speed:

1. **CI builds images** — GitHub Actions builds the Docker image on every push to `main` and pushes to GitHub Container Registry (GHCR)
2. **VM pulls images** — `deploy.py` pulls the pre-built image from GHCR (~30 seconds) instead of building locally (~25 minutes on 1GB VM)
3. **Secrets from Vault** — `deploy.py` fetches secrets from OCI Vault and passes them to containers

### Deploy Commands

```bash
# Standard deploy (pull latest image)
./scripts/deploy.py up -d

# Deploy specific version (for rollback or testing)
./scripts/deploy.py up -d --tag sha-abc1234

# Build locally (fallback if GHCR is unavailable)
./scripts/deploy.py up -d --build
```

## Automatic Deployment

Pushes to `main` automatically deploy to production via GitHub Actions. The workflow:

1. Builds and pushes the Docker image to GHCR
2. SSHs to the production VM with the image tag
3. VM pulls the image, deploys, and health-checks
4. If unhealthy, automatically rolls back to the previous version

### Rollback Behavior

- **Automatic**: If health checks fail after deploy, the previous image is redeployed
- **Manual**: Use `./scripts/deploy.py up -d --tag sha-<commit>` to deploy any version
- **Limitation**: Database migrations are NOT rolled back. If a migration causes issues, manual intervention is required.

### Setting Up Auto-Deploy (One-Time)

See [Appendix: Auto-Deploy Setup](#appendix-auto-deploy-setup) for detailed instructions.

## Secrets Handling

**No secrets are written to disk.** The deployment uses a two-stage approach:

1. **`scripts/deploy.py`** runs on the host, fetches all secrets from OCI Vault using instance principal authentication, and passes them to `docker compose` via environment variables. Secrets exist only in the deploy script's process memory.

2. **Docker containers** receive secrets via environment variables from the deploy script. The Postgres container gets `POSTGRES_PASSWORD`, and the app container gets all other secrets.

This design ensures:
- No `.env` files with production secrets on disk
- No Docker secrets files
- Secrets only exist in process memory
- Vault is the single source of truth

## 1. Create OCI Resources

### 1.1 Create Compute Instance

1. Go to **Compute → Instances → Create Instance**
2. Select **Always Free Eligible** shape:
   - **Ampere A1** (ARM): Up to 4 OCPUs, 24 GB RAM (recommended)
   - **AMD E2.1.Micro**: 1 OCPU, 1 GB RAM
3. Select **Ubuntu 22.04** or **Oracle Linux 8** image
4. Create or select a VCN with public subnet
5. Add your SSH public key
6. Note the public IP and instance OCID after creation

### 1.2 Configure Security List / NSG

Allow only necessary ports:

| Direction | Source/Dest | Protocol | Port | Description |
|-----------|-------------|----------|------|-------------|
| Ingress | 0.0.0.0/0 | TCP | 22 | SSH |
| Ingress | 0.0.0.0/0 | TCP | 80 | HTTP (Caddy redirect) |
| Ingress | 0.0.0.0/0 | TCP | 443 | HTTPS |
| Egress | 0.0.0.0/0 | All | All | Allow outbound |

**Do NOT expose port 5432** — Postgres is only accessible within the Docker network.

### 1.3 Create OCI Vault and Secrets

1. Go to **Identity & Security → Vault → Create Vault**
   - Name: `portfolio-vault`
   - Type: Default (free tier compatible)
   - Note the **Vault OCID**

2. Create a Master Encryption Key:
   - Go to your vault → Master Encryption Keys → Create Key
   - Name: `portfolio-key`
   - Key Shape: AES 256

3. Create secrets (Identity & Security → Vault → your vault → Secrets → Create Secret):

   | OCI Secret Name | Environment Variable | Required | Description |
   |-----------------|---------------------|----------|-------------|
   | `portfolio-secret-key` | `SECRET_KEY` | Yes | Session signing (≥32 chars) |
   | `portfolio-postgres-password` | `POSTGRES_PASSWORD` | Yes | Database password |
   | `portfolio-database-url` | `DATABASE_URL` | Yes | Full Postgres connection URL |
   | `portfolio-google-client-id` | `GOOGLE_CLIENT_ID` | Yes | Google OAuth client ID |
   | `portfolio-google-client-secret` | `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth secret |
   | `portfolio-google-redirect-uri` | `GOOGLE_REDIRECT_URI` | No | OAuth callback URL |
   | `portfolio-cumbuca-redirect-uri` | `CUMBUCA_REDIRECT_URI` | No | Cumbuca callback |
   | `portfolio-allowed-emails` | `ALLOWED_GOOGLE_EMAILS` | No | Email allowlist |
   | `portfolio-ghcr-token` | (internal) | No | GHCR read token for pulling images |

   **Generating secret values:**
   ```bash
   # SECRET_KEY (must be at least 32 characters)
   python -c "import secrets; print(secrets.token_urlsafe(32))"

   # POSTGRES_PASSWORD
   python -c "import secrets; print(secrets.token_urlsafe(24))"

   # DATABASE_URL (use the password you generated above)
   # Format: postgresql+psycopg://portfolio:YOUR_PASSWORD@postgres:5432/portfolio
   ```

### 1.4 Create Dynamic Group for Instance Principal

1. Go to **Identity & Security → Dynamic Groups → Create**
2. Name: `portfolio-instances`
3. Matching rule (replace with your instance OCID):
   ```
   instance.id = 'ocid1.instance.oc1.xxx.yyy'
   ```
   Or match by compartment (less secure, allows all instances):
   ```
   instance.compartment.id = 'ocid1.compartment.oc1..xxx'
   ```

### 1.5 Create IAM Policy

1. Go to **Identity & Security → Policies → Create Policy**
2. Name: `portfolio-secrets-read`
3. Compartment: Your compartment (or root for tenancy-wide)
4. Policy statements:
   ```
   Allow dynamic-group portfolio-instances to read secret-family in compartment <your-compartment>
   ```

### 1.6 Create GitHub Personal Access Token for GHCR

The production image is stored in GitHub Container Registry (GHCR). If the package is private, the VM needs a token to pull images.

1. Go to [GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens](https://github.com/settings/tokens?type=beta)

2. Click **Generate new token**

3. Configure the token:
   - **Token name**: `portfolio-ghcr-pull`
   - **Expiration**: Choose an appropriate expiration (e.g., 90 days, or no expiration)
   - **Repository access**: Select **Only select repositories** → `e-motta/portfolio-manager-v2`
   - **Permissions**: 
     - **Packages**: Read-only (this is all that's needed to pull)

4. Click **Generate token** and copy the token value

5. Create the OCI Vault secret:
   - Go to your OCI Vault → Secrets → Create Secret
   - **Name**: `portfolio-ghcr-token`
   - **Secret Contents**: Paste the GitHub token
   - Click **Create Secret**

**Note**: If you make the GHCR package public, you can skip this step. The deploy script will work without the token for public packages.

**Token rotation**: When the token expires, generate a new one and update the OCI Vault secret. The next deploy will use the new token automatically.

## 2. Configure DNS

Add these records pointing to your VM's public IP:

| Type | Host | Value | TTL |
|------|------|-------|-----|
| A | finance | `<VM-Public-IP>` | 1h |
| AAAA | finance | `<VM-IPv6>` (if available) | 1h |

Wait for DNS propagation: `dig finance.eduardomotta.dev`

## 3. Configure Google OAuth

1. Go to [Google Cloud Console → APIs & Credentials](https://console.cloud.google.com/apis/credentials)
2. Select or create your OAuth 2.0 Client ID
3. Add authorized redirect URI:
   ```
   https://finance.eduardomotta.dev/auth/callback
   ```

## 4. Configure Cumbuca (Optional)

Update your Cumbuca app redirect URI to:
```
https://finance.eduardomotta.dev/auth/cumbuca/callback
```

## 5. Set Up the VM

SSH into your instance:

```bash
ssh ubuntu@<VM-Public-IP>
```

### 5.1 Install Docker and Docker Compose

Ubuntu:
```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt install docker-compose-plugin python3-pip -y
pip3 install --user oci
exit  # Log out and back in for group changes
```

Oracle Linux:
```bash
sudo dnf install -y dnf-utils python3-pip
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
pip3 install --user oci
exit
```

### 5.2 Clone the Repository

```bash
git clone https://github.com/yourusername/portfolio-manager-v2.git
cd portfolio-manager-v2
```

## 6. Deploy with OCI Vault Secrets

### 6.1 Set Vault Environment Variables

```bash
export OCI_VAULT_OCID="ocid1.vault.oc1.xxx.yyy"
export OCI_COMPARTMENT_ID="ocid1.compartment.oc1..xxx"
```

Add these to your shell profile for persistence:
```bash
echo 'export OCI_VAULT_OCID="ocid1.vault.oc1.xxx.yyy"' >> ~/.bashrc
echo 'export OCI_COMPARTMENT_ID="ocid1.compartment.oc1..xxx"' >> ~/.bashrc
```

### 6.2 Deploy Using deploy.py

The deploy script fetches secrets from Vault, pulls the pre-built image from GHCR, and starts the containers:

```bash
./scripts/deploy.py up -d
```

You should see:
```
Authenticating with OCI instance principal...
Fetching secrets from OCI Vault...
  SECRET_KEY: loaded
  POSTGRES_PASSWORD: loaded
  DATABASE_URL: loaded
  GOOGLE_CLIENT_ID: loaded
  GOOGLE_CLIENT_SECRET: loaded
  GHCR token: loaded
  ...

Logging in to ghcr.io...
  Logged in to ghcr.io

Pulling image (tag: latest)...
Running: docker compose -f docker-compose.yml -f docker-compose.production.yml pull app

Running: docker compose -f docker-compose.yml -f docker-compose.production.yml up -d
Logging out from ghcr.io...
```

**Deploy options:**
```bash
# Deploy latest image (default)
./scripts/deploy.py up -d

# Deploy specific version by SHA
./scripts/deploy.py up -d --tag sha-abc1234

# Build locally instead of pulling (slower, but works without GHCR)
./scripts/deploy.py up -d --build
```

### 6.3 Verify Deployment

```bash
# Check all services are running
./scripts/deploy.py ps

# View logs
./scripts/deploy.py logs -f app

# Check app health
curl https://finance.eduardomotta.dev/api/auth/config
```

## 7. Systemd Service for Auto-Start

Create `/etc/systemd/system/portfolio.service`:

```ini
[Unit]
Description=Portfolio Manager
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/portfolio-manager-v2
Environment="OCI_VAULT_OCID=ocid1.vault.oc1.xxx.yyy"
Environment="OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxx"
# Use --build as fallback since systemd starts before network may be fully up
# For faster restarts, consider using a timer to pull the latest image periodically
ExecStart=/home/ubuntu/portfolio-manager-v2/scripts/deploy.py up -d --build
ExecStop=/home/ubuntu/portfolio-manager-v2/scripts/deploy.py down
User=ubuntu

[Install]
WantedBy=multi-user.target
```

Enable the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable portfolio
```

## 8. Backup and Maintenance

### 8.1 Postgres Backup

```bash
./scripts/deploy.py exec postgres pg_dump -U portfolio portfolio > backup_$(date +%Y%m%d).sql
```

### 8.2 Update Application

The image is automatically built and pushed to GHCR when changes are merged to `main`. To deploy the latest version:

```bash
cd portfolio-manager-v2
git pull  # Update deploy.py and compose files if needed
./scripts/deploy.py up -d
```

### 8.3 Rollback to Previous Version

If a deploy causes issues, roll back to a previous image by SHA:

```bash
# Find the SHA of the last known-good commit
git log --oneline -10

# Deploy that specific version
./scripts/deploy.py up -d --tag sha-abc1234
```

Image tags follow the pattern `sha-<7-char-sha>`. You can also see available tags at:
https://github.com/e-motta/portfolio-manager-v2/pkgs/container/portfolio-manager-v2

### 8.4 View Logs

```bash
./scripts/deploy.py logs -f app
./scripts/deploy.py logs -f postgres
./scripts/deploy.py logs -f caddy
```

## Troubleshooting

### Instance principal authentication fails

1. Verify IMDS is reachable:
   ```bash
   curl -s http://169.254.169.254/opc/v2/instance/ | head
   ```

2. Verify dynamic group includes your instance:
   - Check instance OCID matches the dynamic group rule

3. Verify IAM policy allows `read secret-family`

4. Test OCI CLI with instance principal:
   ```bash
   oci os ns get --auth instance_principal
   ```

### Secrets not loading

1. Check secret names match exactly (e.g., `portfolio-secret-key`)
2. Verify secrets are in ACTIVE lifecycle state
3. Run deploy.py with debug output:
   ```bash
   ./scripts/deploy.py up -d --build 2>&1 | head -50
   ```

### App fails validation

If you see `FATAL: Missing required production secrets`:
- Ensure all required secrets exist in OCI Vault
- Check secret values are not empty
- Verify `SECRET_KEY` is at least 32 characters

### Proxy headers / HTTPS issues

The app trusts proxy headers from Docker internal networks (172.x, 192.168.x, 10.x). If you see cookie or redirect issues:

1. Verify Caddy is proxying correctly:
   ```bash
   ./scripts/deploy.py logs caddy
   ```

2. Check X-Forwarded headers are being set:
   ```bash
   ./scripts/deploy.py exec app curl -v http://localhost:8000/api/auth/config
   ```

## Security Checklist

- [ ] Only ports 22, 80, 443 exposed in security list
- [ ] Postgres not exposed to internet (internal Docker network only)
- [ ] All secrets stored in OCI Vault
- [ ] No `.env` files with production secrets on disk
- [ ] Using `deploy.py` (not raw `docker compose`) for deployments
- [ ] Instance principal auth (no API keys on VM)
- [ ] Dynamic group scoped to specific instance OCID
- [ ] `ALLOWED_GOOGLE_EMAILS` set to restrict access
- [ ] Regular backups configured
- [ ] SSH key authentication only (no password)

## Secret Name to Environment Variable Mapping

| OCI Secret Name | Environment Variable | Required |
|-----------------|---------------------|----------|
| `portfolio-secret-key` | `SECRET_KEY` | Yes |
| `portfolio-postgres-password` | `POSTGRES_PASSWORD` | Yes |
| `portfolio-database-url` | `DATABASE_URL` | Yes |
| `portfolio-google-client-id` | `GOOGLE_CLIENT_ID` | Yes |
| `portfolio-google-client-secret` | `GOOGLE_CLIENT_SECRET` | Yes |
| `portfolio-google-redirect-uri` | `GOOGLE_REDIRECT_URI` | No |
| `portfolio-cumbuca-redirect-uri` | `CUMBUCA_REDIRECT_URI` | No |
| `portfolio-allowed-emails` | `ALLOWED_GOOGLE_EMAILS` | No |
| `portfolio-ghcr-token` | (used for docker login) | No |

This mapping is defined in `scripts/deploy.py` and `app/core/vault.py`.

## GHCR Authentication Tradeoff

The deploy script logs out of GHCR after pulling images to avoid leaving credentials in `~/.docker/config.json`. This means:

- **Pro**: No credentials stored on disk between deploys
- **Con**: Manual `docker pull ghcr.io/...` commands won't work outside of deploy.py

If you need passwordless pulls (e.g., for debugging), you can:
1. Make the GHCR package public (Settings → Change visibility), or
2. Run `docker login ghcr.io` manually (credentials will persist until logout)

## Design Tradeoffs

### Why deploy.py instead of in-app Vault loading?

The app also loads secrets from Vault at startup (for app-level secrets like `SECRET_KEY`). However, the **Postgres container** needs `POSTGRES_PASSWORD` before the app starts. Options considered:

1. **Custom Postgres image with OCI SDK** — Complex, hard to maintain
2. **Docker secrets with tmpfs** — Still requires something to populate them
3. **Trust auth within Docker network** — Security concern
4. **deploy.py wrapper** — Simple, no secrets on disk, works with any container

We chose option 4: `deploy.py` fetches all secrets including `POSTGRES_PASSWORD` and passes them via environment variables. This keeps the standard Postgres image and ensures no secrets touch the filesystem.

### Instance principal vs config file

Instance principal authentication requires no credentials on the VM — the VM's identity is used automatically. This is more secure than storing API keys in a config file.

---

## Appendix: Auto-Deploy Setup

This section covers one-time setup for automatic deployment from GitHub Actions.

### A.1 Generate Deploy Key (on your local machine)

```bash
# Generate a dedicated ed25519 key pair for deploy
ssh-keygen -t ed25519 -C "github-deploy@portfolio-manager" -f ~/.ssh/deploy_ed25519 -N ""

# Display the private key (add to GitHub secret DEPLOY_SSH_KEY)
cat ~/.ssh/deploy_ed25519

# Display the public key (add to authorized_keys on VM)
cat ~/.ssh/deploy_ed25519.pub
```

### A.2 Configure authorized_keys on the VM

Add the public key to the deploy user's `authorized_keys` with forced command:

```bash
# On the VM, as root or the deploy user
cat >> /home/ubuntu/.ssh/authorized_keys << 'EOF'
restrict,command="/opt/portfolio-manager-v2/scripts/remote-deploy.sh" ssh-ed25519 AAAA...your-public-key... github-deploy@portfolio-manager
EOF
```

**Authorized keys line format:**

```
restrict,command="/opt/portfolio-manager-v2/scripts/remote-deploy.sh" <key-type> <key-data> <comment>
```

The `restrict` keyword disables port forwarding, agent forwarding, X11 forwarding, PTY allocation, and all other features. Only the forced command is executed, regardless of what the client requests.

### A.3 Set Up VM Environment

```bash
# Create the deploy environment file (root-owned, non-secret OCIDs)
sudo mkdir -p /etc/portfolio
sudo tee /etc/portfolio/deploy.env << 'EOF'
OCI_VAULT_OCID="ocid1.vault.oc1.xxx.yyy"
OCI_COMPARTMENT_ID="ocid1.compartment.oc1..xxx"
EOF
sudo chmod 644 /etc/portfolio/deploy.env
sudo chown root:root /etc/portfolio/deploy.env

# Create Python venv with OCI SDK for deploy.py
sudo python3 -m venv /opt/portfolio-venv
sudo /opt/portfolio-venv/bin/pip install oci

# Clone/update the repository
sudo mkdir -p /opt/portfolio-manager-v2
sudo chown ubuntu:ubuntu /opt/portfolio-manager-v2
git clone https://github.com/e-motta/portfolio-manager-v2.git /opt/portfolio-manager-v2

# Make the deploy script executable
chmod +x /opt/portfolio-manager-v2/scripts/remote-deploy.sh
```

### A.4 Verify SSH Host Key Fingerprint

Get the VM's SSH host key fingerprint and verify it:

```bash
# On the VM
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Then use `ssh-keyscan` to get the known_hosts entry:

```bash
# On your local machine (or GitHub Actions will use this)
ssh-keyscan -t ed25519 <VM-IP-or-hostname> 2>/dev/null

# Verify the fingerprint matches what the VM shows
ssh-keyscan <VM-IP-or-hostname> 2>/dev/null | ssh-keygen -lf -
```

### A.5 Configure GitHub Secrets and Environment

1. Go to **Repository → Settings → Environments → New environment**
2. Name: `production`
3. Enable **Required reviewers** if you want manual approval (optional)
4. Under **Deployment branches and tags**, select **Selected branches and tags**
5. Add rule: **Branch name pattern**: `main`

Then add these secrets under **Repository → Settings → Secrets and variables → Actions → Repository secrets**:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `DEPLOY_SSH_KEY` | Private key contents | The ed25519 private key (including `-----BEGIN/END-----`) |
| `DEPLOY_KNOWN_HOSTS` | `ssh-keyscan` output | The host key line from ssh-keyscan |
| `DEPLOY_HOST` | VM IP or hostname | e.g., `finance.eduardomotta.dev` or `129.146.x.y` |
| `DEPLOY_USER` | SSH username | Usually `ubuntu` or `opc` |

**Important**: All four secrets must be scoped to the `production` environment or be repository-level secrets.

### A.6 Test the Connection

Before the first automated deploy, test SSH access:

```bash
# Locally, test with the same command GitHub Actions will use
ssh -i ~/.ssh/deploy_ed25519 \
    -o StrictHostKeyChecking=yes \
    ubuntu@<VM-IP> \
    "sha-0000000"
```

This should fail with "Invalid tag format" (since that tag doesn't exist), but it proves SSH and the forced command work.

### A.7 Manual Rollback

If an automated deployment causes issues and you need to roll back manually:

```bash
# SSH to the VM
ssh ubuntu@<VM-IP>

# Find a working previous version
git -C /opt/portfolio-manager-v2 log --oneline -10

# Deploy that version
cd /opt/portfolio-manager-v2
./scripts/deploy.py up -d --tag sha-abc1234
```

Or use the remote deploy script directly with a known-good tag:

```bash
SSH_ORIGINAL_COMMAND="sha-abc1234" /opt/portfolio-manager-v2/scripts/remote-deploy.sh
```

**Important**: Database migrations are NOT automatically rolled back. If a migration caused the issue, you must manually apply a reverse migration or restore from backup.

### A.8 Viewing Deploy History

The deploy script logs all deployments to `/opt/portfolio-manager-v2/deploy-history.log`:

```bash
# View recent deploys
tail -50 /opt/portfolio-manager-v2/deploy-history.log

# Watch deploys in real-time
tail -f /opt/portfolio-manager-v2/deploy-history.log
```
