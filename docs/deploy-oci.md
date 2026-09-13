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
│       │               │    ┌──────────────┘             │
│       │               │    ▼                            │
│       │               │  postgres_data                  │
│       │               │  (volume)                       │
│       │               ▼                                 │
│       │          OCI Vault                              │
│       │          (secrets)                              │
└───────│─────────────────────────────────────────────────┘
        │
        ▼
   Internet (:443)
```

**Secrets Handling**: The app loads secrets directly from OCI Vault at startup using the OCI Python SDK with instance principal authentication. Secrets are held in memory only — **no secrets are written to disk**.

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

   | OCI Secret Name | App Setting | Description |
   |-----------------|-------------|-------------|
   | `portfolio-secret-key` | `SECRET_KEY` | Session signing key (≥32 chars) |
   | `portfolio-database-url` | `DATABASE_URL` | Full Postgres URL |
   | `portfolio-postgres-password` | `POSTGRES_PASSWORD` | DB password (for postgres container) |
   | `portfolio-google-client-id` | `GOOGLE_CLIENT_ID` | Google OAuth client ID |
   | `portfolio-google-client-secret` | `GOOGLE_CLIENT_SECRET` | Google OAuth secret |
   | `portfolio-google-redirect-uri` | `GOOGLE_REDIRECT_URI` | `https://finance.eduardomotta.dev/auth/callback` |
   | `portfolio-cumbuca-redirect-uri` | `CUMBUCA_REDIRECT_URI` | Cumbuca callback (optional) |
   | `portfolio-allowed-emails` | `ALLOWED_GOOGLE_EMAILS` | Email allowlist (optional) |

   **Generating secret values:**
   ```bash
   # SECRET_KEY
   python -c "import secrets; print(secrets.token_urlsafe(32))"

   # POSTGRES_PASSWORD
   python -c "import secrets; print(secrets.token_urlsafe(24))"

   # DATABASE_URL (use the postgres password you generated)
   # postgresql+psycopg://portfolio:PASSWORD@postgres:5432/portfolio
   ```

### 1.4 Create Dynamic Group for Instance Principal

1. Go to **Identity & Security → Dynamic Groups → Create**
2. Name: `portfolio-instances`
3. Matching rule (replace with your instance OCID):
   ```
   instance.id = 'ocid1.instance.oc1.xxx.yyy'
   ```
   Or match by compartment (allows all instances in compartment):
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
   Or for tenancy-wide:
   ```
   Allow dynamic-group portfolio-instances to read secret-family in tenancy
   ```

## 2. Configure DNS

### Squarespace DNS (or your provider)

Add these records pointing to your VM's public IP:

| Type | Host | Value | TTL |
|------|------|-------|-----|
| A | finance | `<VM-Public-IP>` | 1h |
| AAAA | finance | `<VM-IPv6>` (if available) | 1h |

Wait for DNS propagation (check with `dig finance.eduardomotta.dev`).

## 3. Configure Google OAuth

1. Go to [Google Cloud Console → APIs & Credentials](https://console.cloud.google.com/apis/credentials)
2. Select or create your OAuth 2.0 Client ID
3. Add authorized redirect URI:
   ```
   https://finance.eduardomotta.dev/auth/callback
   ```
4. If using Google Drive backups, the same URI is used for Drive OAuth.

## 4. Configure Cumbuca (Optional)

If using Cumbuca Open Finance:

1. Update your Cumbuca app redirect URI to:
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
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Log out and back in for group changes
exit
```

Oracle Linux:
```bash
sudo dnf install -y dnf-utils
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
exit
```

### 5.2 Clone the Repository

```bash
git clone https://github.com/yourusername/portfolio-manager-v2.git
cd portfolio-manager-v2
```

## 6. Deploy with OCI Vault Secrets

### 6.1 Configure Environment

Create `.env.production` with your OCI Vault configuration:

```bash
cat > .env.production << 'EOF'
APP_ENV=production
OCI_VAULT_OCID=ocid1.vault.oc1.xxx.yyy
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxx
EOF

chmod 600 .env.production
```

**Note**: The app loads all other secrets (SECRET_KEY, DATABASE_URL, Google OAuth, etc.) directly from OCI Vault at startup. Only the Vault OCID and Compartment ID are needed in the config file.

### 6.2 Start the Application

```bash
# Build and start all services
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build

# Watch startup logs (secrets are loaded at app startup)
docker compose logs -f app

# Verify all services are healthy
docker compose ps
```

You should see log messages like:
```
Loading secrets from OCI Vault...
  Loaded: SECRET_KEY
  Loaded: DATABASE_URL
  Loaded: GOOGLE_CLIENT_ID
  ...
Loaded N secrets from OCI Vault
```

## 7. Alternative: Deploy without OCI Vault

If not using OCI Vault (simpler but less secure):

```bash
# Copy example and fill in ALL values
cp .env.production.example .env.production
nano .env.production

# Comment out OCI_VAULT_OCID and OCI_COMPARTMENT_ID
# Set all secrets directly in the file

# Start services (use base compose only)
docker compose up -d --build
```

**Important**: Ensure `.env.production` has restrictive permissions:
```bash
chmod 600 .env.production
```

## 8. Post-Deployment

### 8.1 Verify Deployment

```bash
# Check Caddy got TLS certificate
docker compose logs caddy | grep -i certificate

# Test the application
curl -I https://finance.eduardomotta.dev

# Check app health
curl https://finance.eduardomotta.dev/api/auth/config
```

### 8.2 Create Systemd Service (Auto-start)

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
ExecStartPre=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.production.yml pull
ExecStart=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.production.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.production.yml down
User=ubuntu

[Install]
WantedBy=multi-user.target
```

Enable the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable portfolio
```

## 9. Backup and Maintenance

### 9.1 Postgres Backup

Manual backup:
```bash
docker compose exec postgres pg_dump -U portfolio portfolio > backup_$(date +%Y%m%d).sql
```

Automated daily backup (add to crontab):
```bash
0 3 * * * cd /home/ubuntu/portfolio-manager-v2 && docker compose exec -T postgres pg_dump -U portfolio portfolio | gzip > /home/ubuntu/backups/portfolio_$(date +\%Y\%m\%d).sql.gz
```

### 9.2 Restore from Backup

```bash
# Stop the app
docker compose stop app

# Restore
gunzip -c backup_20260913.sql.gz | docker compose exec -T postgres psql -U portfolio portfolio

# Restart
docker compose start app
```

### 9.3 Update Application

```bash
cd portfolio-manager-v2
git pull
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
```

### 9.4 View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f app
docker compose logs -f postgres
docker compose logs -f caddy
```

## Troubleshooting

### Caddy not getting TLS certificate

1. Verify DNS is resolving correctly:
   ```bash
   dig finance.eduardomotta.dev
   ```
2. Check Caddy logs:
   ```bash
   docker compose logs caddy
   ```
3. Ensure ports 80 and 443 are open in security list

### App fails to start

1. Check app logs for Vault loading errors:
   ```bash
   docker compose logs app | grep -i vault
   ```
2. Verify OCI_VAULT_OCID and OCI_COMPARTMENT_ID are set:
   ```bash
   docker compose exec app env | grep OCI
   ```
3. Verify Postgres is healthy:
   ```bash
   docker compose ps postgres
   docker compose logs postgres
   ```

### OCI Vault secrets not loading

1. Check app logs for specific errors:
   ```bash
   docker compose logs app 2>&1 | head -50
   ```

2. Verify instance principal is working (run on the VM, not in container):
   ```bash
   # Install OCI CLI if needed
   oci os ns get --auth instance_principal
   ```

3. Verify dynamic group includes your instance:
   - Check instance OCID matches the dynamic group rule
   - Check the dynamic group is in the correct compartment

4. Verify IAM policy:
   - Policy must allow `read secret-family`
   - Policy must reference the correct dynamic group name
   - Policy must be in the correct compartment (or root)

5. Verify secrets exist in Vault:
   - Check secret names match exactly (e.g., `portfolio-secret-key`)
   - Check secrets are in ACTIVE lifecycle state

### Database connection issues

1. Check if Postgres is running:
   ```bash
   docker compose exec postgres pg_isready -U portfolio
   ```
2. Verify DATABASE_URL was loaded from Vault:
   ```bash
   docker compose logs app | grep DATABASE
   ```

### Container can't reach OCI IMDS

The OCI Instance Metadata Service (IMDS) at `169.254.169.254` must be reachable from containers for instance principal auth. This works by default on OCI, but if you have custom network configuration:

1. Verify IMDS is reachable from the host:
   ```bash
   curl -s http://169.254.169.254/opc/v2/instance/ | head
   ```

2. Verify from inside the container:
   ```bash
   docker compose exec app curl -s http://169.254.169.254/opc/v2/instance/ | head
   ```

## Security Checklist

- [ ] Only ports 22, 80, 443 exposed in security list
- [ ] Postgres not exposed to internet (internal Docker network only)
- [ ] Secrets stored in OCI Vault, loaded in-memory only
- [ ] No secrets written to disk (no .env files with production secrets)
- [ ] Instance principal used (no API keys or config files on VM)
- [ ] Dynamic group scoped to specific instance (not entire compartment)
- [ ] `ALLOWED_GOOGLE_EMAILS` set to restrict access
- [ ] Regular backups configured
- [ ] SSH key authentication only (no password)

## Secret Name to Environment Variable Mapping

The app loads these secrets from OCI Vault and maps them to environment variables:

| OCI Secret Name | Environment Variable | Required |
|-----------------|---------------------|----------|
| `portfolio-secret-key` | `SECRET_KEY` | Yes |
| `portfolio-database-url` | `DATABASE_URL` | Yes |
| `portfolio-postgres-password` | `POSTGRES_PASSWORD` | Yes |
| `portfolio-google-client-id` | `GOOGLE_CLIENT_ID` | Yes |
| `portfolio-google-client-secret` | `GOOGLE_CLIENT_SECRET` | Yes |
| `portfolio-google-redirect-uri` | `GOOGLE_REDIRECT_URI` | Yes |
| `portfolio-cumbuca-redirect-uri` | `CUMBUCA_REDIRECT_URI` | No |
| `portfolio-allowed-emails` | `ALLOWED_GOOGLE_EMAILS` | No |

This mapping is defined in `app/core/vault.py`.
