#!/bin/bash
set -e

echo "🔧 Setting up Syncthing correctly for ROOT..."

# 1. Install if missing
if ! command -v syncthing >/dev/null; then
  echo "📦 Installing syncthing..."
  apt update && apt install -y syncthing
fi

# 2. Stop any running instances
echo "🛑 Stopping existing Syncthing processes..."
systemctl stop syncthing@root 2>/dev/null || true
pkill syncthing || true

# 3. Generate config if not present
CONFIG="/root/.local/state/syncthing/config.xml"
if [[ ! -f "$CONFIG" ]]; then
  echo "⚙️  Generating initial syncthing config..."
  syncthing --no-browser --no-restart --generate="/root/.local/state/syncthing"
  sleep 2
fi

# 4. Update bind address to 0.0.0.0
echo "🌐 Setting GUI listen address to 0.0.0.0:8384..."
sed -i 's|<address>.*:8384</address>|<address>0.0.0.0:8384</address>|' "$CONFIG"

# 5. Create proper systemd service for root
SERVICE="/etc/systemd/system/syncthing-root.service"
echo "⚙️  Creating systemd service at $SERVICE"

cat > "$SERVICE" << 'SVC'
[Unit]
Description=Syncthing - Root Service
After=network.target

[Service]
User=root
ExecStart=/usr/bin/syncthing serve --no-browser --no-restart --logflags=0
Restart=on-failure
RestartSec=5
SuccessExitStatus=3 4
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
SVC

# 6. Enable & start service
echo "✅ Enabling and starting service..."
systemctl daemon-reload
systemctl enable syncthing-root
systemctl restart syncthing-root

# 7. Verify
sleep 3
echo "🔍 Checking if Syncthing GUI is listening on 0.0.0.0:8384..."
ss -tulpn | grep 8384 || echo "⚠️  Port 8384 not detected! Something went wrong."

echo "✅ Syncthing setup complete!"
echo "🌍 Access it at: http://<SERVER-IP>:8384"
