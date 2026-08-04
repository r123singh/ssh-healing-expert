#!/usr/bin/env bash
# Run inside Ubuntu WSL to prepare the demo service + SSH.
# From PowerShell:  wsl -d Ubuntu -e bash -lc "bash /mnt/d/Flytxt/CCAD/ssh-service-demo/setup-wsl-target.sh"

set -euo pipefail

SERVICE_NAME="billing-api"
APP_DIR="/opt/billing-api"
LOG_DIR="/var/log/billing-api"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "==> Enabling systemd (if needed)"
if [ ! -f /etc/wsl.conf ] || ! grep -q "systemd=true" /etc/wsl.conf 2>/dev/null; then
  sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[boot]
systemd=true
EOF
  echo "Wrote /etc/wsl.conf — run from PowerShell:  wsl --shutdown"
  echo "Then reopen WSL and re-run this script."
  exit 0
fi

echo "==> Installing openssh-server (if needed)"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server python3

echo "==> Starting SSH"
sudo systemctl enable --now ssh

echo "==> Creating demo app at ${APP_DIR}"
sudo mkdir -p "${APP_DIR}" "${LOG_DIR}"
sudo tee "${APP_DIR}/app.py" >/dev/null <<'PY'
#!/usr/bin/env python3
"""Tiny demo HTTP service for self-healing demos."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s billing-api[%(process)d]: %(message)s",
    datefmt="%b %d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/var/log/billing-api/application.log"),
    ],
)
log = logging.getLogger("billing-api")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            log.info("GET %s 200 OK", self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK\n")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        return

def main():
    log.info("Loading configuration from /opt/billing-api/config.yaml")
    log.info("Connecting to database...")
    log.info("Database connection established")
    log.info("Server listening on 0.0.0.0:8080")
    log.info("billing-api started successfully - ready to accept requests")
    log.info("Health check passed - all dependencies OK")
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()

if __name__ == "__main__":
    main()
PY
sudo chmod +x "${APP_DIR}/app.py"
echo "port: 8080" | sudo tee "${APP_DIR}/config.yaml" >/dev/null
sudo chmod 777 "${LOG_DIR}"

echo "==> Installing systemd unit"
sudo tee "${UNIT_FILE}" >/dev/null <<EOF
[Unit]
Description=Billing API Demo Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${APP_DIR}/app.py
Restart=on-failure
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.service"

WSL_USER="$(whoami)"
echo "==> Passwordless sudo for agent systemctl commands"
SUDOERS_FILE="/etc/sudoers.d/billing-api-agent"
sudo tee "${SUDOERS_FILE}" >/dev/null <<EOF
${WSL_USER} ALL=(root) NOPASSWD: /bin/systemctl is-active ${SERVICE_NAME}.service, /bin/systemctl status ${SERVICE_NAME}.service, /bin/systemctl stop ${SERVICE_NAME}.service, /bin/systemctl start ${SERVICE_NAME}.service, /bin/systemctl restart ${SERVICE_NAME}.service
EOF
sudo chmod 440 "${SUDOERS_FILE}"
sudo visudo -cf "${SUDOERS_FILE}"
sudo -n systemctl is-active "${SERVICE_NAME}.service" >/dev/null
echo "  sudo -n systemctl ... OK for ${WSL_USER}"

echo "==> Status"
systemctl is-active "${SERVICE_NAME}.service"
systemctl status "${SERVICE_NAME}.service" --no-pager || true

WSL_IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "WSL setup complete."
echo "  User : ${WSL_USER}"
echo "  IP   : ${WSL_IP}"
echo "  SSH  : ssh ${WSL_USER}@${WSL_IP}"
echo "  Svc  : ${SERVICE_NAME}.service"
echo ""
echo "Next (PowerShell): copy those values into ssh-service-demo\\.env"
