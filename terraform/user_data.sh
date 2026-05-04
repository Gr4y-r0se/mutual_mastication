#!/bin/bash
# Bootstrap script for meat-ensemble on Amazon Linux 2023 (ARM64 / Graviton2)
# Rendered by Terraform templatefile — ${VAR} is Terraform, $VAR is shell.
set -euo pipefail
exec > /var/log/user_data.log 2>&1

# ── Terraform-injected configuration ────────────────────────────────────────
APP_NAME="${app_name}"
REPO_URL="${repo_url}"
DOMAIN="${domain_name}"
SECRET_KEY="${secret_key}"
CERTBOT_EMAIL="${certbot_email}"
CERTBOT_DOMAINS="${certbot_domains}"
NGINX_SERVER_NAME="${server_name}"

# ── Derived paths ────────────────────────────────────────────────────────────
APP_USER="appuser"
APP_DIR="/opt/$APP_NAME"
SOCKET_DIR="/run/$APP_NAME"

# ── System packages ──────────────────────────────────────────────────────────
dnf update -y
dnf install -y python3 python3-pip git nginx augeas-libs

# certbot is not in AL2023 repos — install via pip
pip3 install certbot certbot-nginx

# ── App user ─────────────────────────────────────────────────────────────────
useradd -r -s /sbin/nologin -d "$APP_DIR" "$APP_USER"

# ── Clone & install app ──────────────────────────────────────────────────────
git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt gunicorn

# Store the secret key where config.py looks for it
printf '%s' "$SECRET_KEY" > "$APP_DIR/.secret_key"
chmod 600 "$APP_DIR/.secret_key"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ── Gunicorn systemd service ─────────────────────────────────────────────────
# nginx reads the socket, so nginx user needs access — add it to app group
usermod -aG "$APP_USER" nginx

cat > "/etc/systemd/system/$APP_NAME.service" << EOF
[Unit]
Description=$APP_NAME gunicorn daemon
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="SECURE_COOKIES=1"
ExecStart=$APP_DIR/venv/bin/gunicorn \\
    --workers 2 \\
    --bind unix:$SOCKET_DIR/app.sock \\
    --umask 007 \\
    --timeout 60 \\
    "app:create_app()"
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RuntimeDirectory=$APP_NAME
RuntimeDirectoryMode=0750

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$APP_NAME"

# ── nginx config (HTTP only until certbot adds SSL) ──────────────────────────
# Adapted from the project's nginx.conf
cat > "/etc/nginx/conf.d/$APP_NAME.conf" << 'NGINX_CONF_EOF'
limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;

upstream meat_ensemble_upstream {
    server unix:SOCKET_PLACEHOLDER fail_timeout=0;
}

server {
    listen      80;
    listen      [::]:80;
    server_name SERVER_NAME_PLACEHOLDER;

    # Let's Encrypt HTTP-01 challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location = /login {
        limit_req        zone=login burst=5 nodelay;
        limit_req_status 429;
        proxy_pass         http://meat_ensemble_upstream;
        proxy_redirect     off;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass         http://meat_ensemble_upstream;
        proxy_redirect     off;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        client_max_body_size 64k;
    }
}
NGINX_CONF_EOF

# Substitute the placeholders written above (avoids heredoc variable-expansion issues)
sed -i "s|SOCKET_PLACEHOLDER|$SOCKET_DIR/app.sock|g" "/etc/nginx/conf.d/$APP_NAME.conf"
sed -i "s|SERVER_NAME_PLACEHOLDER|$NGINX_SERVER_NAME|g" "/etc/nginx/conf.d/$APP_NAME.conf"

mkdir -p /var/www/certbot
systemctl enable --now nginx

# ── certbot setup service (retries until DNS has propagated) ─────────────────
# Runs asynchronously so this script exits quickly.
# Once the Route53 A record propagates, certbot gets the cert and nginx is
# automatically reconfigured with HTTPS + HSTS.
cat > /usr/local/bin/certbot-setup.sh << EOF
#!/bin/bash
set -euo pipefail
exec >> /var/log/certbot-setup.log 2>&1

for attempt in \$(seq 1 30); do
    echo "[\$(date)] certbot attempt \$attempt..."
    if certbot --nginx \\
        $CERTBOT_DOMAINS \\
        --non-interactive --agree-tos \\
        -m $CERTBOT_EMAIL \\
        --redirect; then
        echo "[\$(date)] Certificate issued successfully."
        # Enable the renewal cron
        echo "0 3 * * * root certbot renew --quiet" > /etc/cron.d/certbot-renew
        systemctl reload nginx
        exit 0
    fi
    echo "[\$(date)] Attempt \$attempt failed — waiting 60s before retry..."
    sleep 60
done

echo "[\$(date)] All 30 attempts failed. Check DNS propagation and re-run manually:"
echo "  certbot --nginx $CERTBOT_DOMAINS --non-interactive --agree-tos -m $CERTBOT_EMAIL --redirect"
EOF
chmod +x /usr/local/bin/certbot-setup.sh

cat > /etc/systemd/system/certbot-setup.service << 'UNIT_EOF'
[Unit]
Description=Initial Let's Encrypt certificate setup
After=network-online.target nginx.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/certbot-setup.sh

[Install]
WantedBy=multi-user.target
UNIT_EOF

systemctl daemon-reload
systemctl enable --now certbot-setup

echo "[$(date)] Bootstrap complete. Certbot running in background — check /var/log/certbot-setup.log"
