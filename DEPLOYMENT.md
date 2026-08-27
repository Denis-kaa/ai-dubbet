# AI Dubber Deployment Guide

> **Важно для текущего проекта:** этот документ содержит исторические примеры окружения `/opt/xadichai`, старого IP и Supervisor. Для текущего production `whimco` используйте `HANDOFF.md`, `deploy/nginx.conf` и systemd-сервисы в `/opt/ai-dubber`. Не запускайте команды из исторических разделов без адаптации.

## Overview
This guide covers deploying the AI Dubber application with frontend, backend, and automated CI/CD pipeline.

## Architecture
- **Frontend**: Next.js static build served via Nginx
- **Backend**: FastAPI application (Python) on port 8000
- **Worker**: Celery worker for video processing
- **Database**: PostgreSQL (port 5432)
- **Cache**: Redis (port 6379)
- **Reverse Proxy**: Nginx with SSL termination

## Pre-deployment Requirements

### Server Requirements
- Ubuntu 20.04+ LTS
- 4GB+ RAM
- 20GB+ Disk Space
- Public IP with domain DNS configured

### Required Dependencies
```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv postgresql redis-server nginx supervisor certbot python3-certbot-nginx
```

## Server Setup

### 1. SSH Connection
```bash
ssh -i ~/.ssh/id_ed25519_xadichai ubuntu@51.21.35.247
```

### 2. Create User (if not exists)
```bash
sudo adduser linuxuser
sudo usermod -aG sudo linuxuser
```

### 3. Create Virtual Environment
```bash
sudo mkdir -p /opt/xadichai
cd /opt/xadichai
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Python Dependencies
```bash
cd /opt/xadichai/backend
pip install -r requirements.txt
```

### 5. Database Setup (PostgreSQL)
```bash
sudo -u postgres psql

CREATE DATABASE dubber_db;
CREATE USER <db_user> WITH PASSWORD '<db_password>';
-- Выдайте только необходимые права пользователю БД; SUPERUSER для production не нужен.
GRANT ALL PRIVILEGES ON DATABASE <db_name> TO <db_user>;
\q

sudo systemctl restart postgresql
```

### 6. Redis Setup
```bash
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### 7. Upload Application Files
```bash
# On local machine
tar czf xadichai-update.tar.gz --exclude='.git' --exclude='.next' --exclude='node_modules' \
  --exclude='*.pyc' --exclude='__pycache__' frontend backend .env server_env_setup.sh

# Upload and extract on server
scp xadichai-update.tar.gz ubuntu@51.21.35.247:/opt/xadichai/
ssh -i ~/.ssh/id_ed25519_xadichai ubuntu@51.21.35.247
cd /opt/xadichai
tar xzf xadichai-update.tar.gz
```

### 8. Configure Environment Variables
```bash
cd /opt/xadichai
cat > .env << 'ENVEOF'
# Add your API keys and configuration here
OPENAI_API_KEY="your-key"
...
ENVEOF
```

### 9. Setup Services with Supervisor
Create `/etc/supervisor/conf.d/xadichai.conf`:
```ini
[program:ai-dubber-api]
command=/opt/xadichai/venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
directory=/opt/xadichai
user=ubuntu
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/ai-dubber/api.log
environment=PYTHONPATH="/opt/xadichai"
stopwaitsecs=10

[program:ai-dubber-worker]
command=/opt/xadichai/venv/bin/celery -A backend.workers.celery_app worker -l info -Q video_processing -c 2
directory=/opt/xadichai
user=ubuntu
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/ai-dubber/worker.log
environment=PYTHONPATH="/opt/xadichai"
stopwaitsecs=10
```

```bash
sudo systemctl restart supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start ai-dubber-api ai-dubber-worker
```

### 10. Frontend Build & Deployment

#### Using Next.js Build
```bash
cd /opt/xadichai/frontend
npm install
npm run build

# Copy build artifacts
sudo mkdir -p /var/www/xadichai.uz/public
sudo rsync -avz --delete .next/standalone/ /var/www/xadichai.uz/public/
sudo chown -R ubuntu:ubuntu /var/www/xadichai.uz
```

#### Alternative: Static Export
```bash
cd /opt/xadichai/frontend
npm install
next build
next export

# Copy to web root
sudo mkdir -p /var/www/xadichai.uz
sudo cp -r out/* /var/www/xadichai.uz/
```

### 11. Configure Nginx

```bash
sudo tee /etc/nginx/sites-available/xadichai << 'NGINXCONFIG'
server {
    listen 80;
    listen [::]:80;
    server_name xadichai.uz;

    root /var/www/xadichai.uz/public;
    index index.html;

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name xadichai.uz;

    root /var/www/xadichai.uz/public;
    index index.html;

    ssl_certificate /etc/letsencrypt/live/xadichai.uz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/xadichai.uz/privkey.pem;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /graphql {
        proxy_pass http://127.0.0.1:8000/graphql;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINXCONFIG

sudo ln -sf /etc/nginx/sites-available/xadichai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 12. Setup SSL with Certbot
```bash
sudo certbot certonly --nginx -d xadichai.uz --agree-tos --non-interactive \
  --email contact@xadichai.uz
```

## CI/CD Pipeline

### Setup GitHub Secrets
Navigate to repository Settings → Secrets and variables → Actions:
- `SSH_PRIVATE_KEY` - Your private SSH key for deploying to the server
- `OPENAI_API_KEY` - OpenAI API key
- `AZURE_SPEECH_KEY` - Azure speech API key
- `CLICK_MERCHANT_ID` - Click payment merchant ID
- `CLICK_SERVICE_ID` - Click payment service ID
- `CLICK_SECRET_KEY` - Click payment secret key
- `DOCKER_USERNAME` - Docker Hub username
- `DOCKER_PASSWORD` - Docker Hub password

### Trigger Deployment
Push to main branch:
```bash
git add .
git commit -m "deploy: production deployment"
git push origin main
```

The CI/CD pipeline will automatically:
1. Run tests on frontend and backend
2. Build Docker images
3. Deploy to the server
4. Update services
5. Reload Nginx

## Monitoring & Maintenance

### Check Service Status
```bash
sudo supervisorctl status
```

### View Logs
```bash
# API logs
sudo tail -f /var/log/ai-dubber/api.log

# Worker logs
sudo tail -f /var/log/ai-dubber/worker.log

# Docker logs
sudo docker logs -f ai-dubber-api
sudo docker logs -f ai-dubber-worker
```

### Database Backup
```bash
# Backup database
pg_dump -U dubber dubber_db > backup_$(date +%Y%m%d).sql

# Restore database
psql -U dubber dubber_db < backup_20240101.sql
```

### SSL Certificate Renewal
```bash
sudo certbot renew --dry-run
```

Certbot automatically renews certificates monthly.

### Update Application
```bash
# SSH to server
ssh -i ~/.ssh/id_ed25519_xadichai ubuntu@51.21.35.247

# Pull latest changes
cd /opt/xadichai
git pull origin main

# Setup environment
./server_env_setup.sh

# Restart services
sudo supervisorctl restart ai-dubber-api ai-dubber-worker

# Update frontend build
cd /opt/xadichai/frontend
npm install
npm run build
sudo rsync -avz --delete .next/standalone/ /var/www/xadichai.uz/public/
sudo nginx -t
sudo systemctl reload nginx
```

## Troubleshooting

### 502 Bad Gateway
1. Check if services are running: `sudo supervisorctl status`
2. Check service logs: `sudo tail -f /var/log/ai-dubber/api.log`
3. Check Nginx error logs: `sudo tail -f /var/log/nginx/error.log`
4. Verify backend is running: `curl http://localhost:8000/health`

### SSL Certificate Issues
```bash
# Check certificate status
sudo systemctl status certbot.timer

# Force renewal
sudo certbot renew --force-renewal
sudo nginx -t
sudo systemctl reload nginx
```

### Database Connection Issues
1. Verify Postgres is running: `sudo systemctl status postgresql`
2. Check database connectivity: `psql -U dubber -d dubber_db`
3. Check .env file for correct credentials

### Frontend Build Issues
```bash
# Clean and rebuild
cd /opt/xadichai/frontend
rm -rf .next
npm install
npm run build
```

## Security Best Practices

1. Firewall Configuration
   - Only allow SSH on port 22
   - Only allow HTTP/HTTPS (80/443)
   - Use ufw:
     ```bash
     sudo ufw allow ssh
     sudo ufw allow 80
     sudo ufw allow 443
     sudo ufw enable
     ```

2. Regular Updates
   ```bash
   sudo apt-get update && sudo apt-get upgrade
   sudo supervisorctl update
   ```

3. Backup Strategy
   - Automated database backups
   - Regular file system backups
   - Test restores regularly

4. Security Hardening
   - Disable password authentication for SSH
   - Use key-based authentication only
   - Enable fail2ban for brute force protection
   - Update Nginx and other packages regularly

## Notes

- The API backend handles requests at: `/api/` and `/graphql`
- The frontend acts as a SPA with routing handled by Nginx
- All API requests go through Nginx reverse proxy
- Environment variables are stored in `/opt/xadichai/.env`
- Service logs are stored in `/var/log/ai-dubber/`
