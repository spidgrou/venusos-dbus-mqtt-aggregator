#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Variables ---
GITHUB_USER="spidgrou"
GITHUB_REPO="venusos-dbus-mqtt-aggregator"
SCRIPT_NAME="dbus_to_mqtt_bridge.py"
SERVICE_NAME="dbus-mqtt-bridge"

# URL to download the raw Python script from GitHub
SCRIPT_URL="https://raw.githubusercontent.com/$GITHUB_USER/$GITHUB_REPO/main/$SCRIPT_NAME"

# Installation paths on the Cerbo GX
DEST_DIR="/data/$SERVICE_NAME"
SERVICE_DIR="/data/service/$SERVICE_NAME"

# --- Start of Script ---
echo "--- Starting D-Bus to MQTT Bridge Service Installation ---"

# 1. Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as the root user."
    exit 1
fi

# 2. Install software dependencies
echo "[1/6] Installing dependencies (python3-paho-mqtt)..."
opkg update > /dev/null
opkg install python3-paho-mqtt > /dev/null
echo "Dependencies installed."

# 3. Download the Python script from GitHub
echo "[2/6] Creating directory and downloading the main script..."
mkdir -p "$DEST_DIR"
if curl -fsSL "$SCRIPT_URL" -o "$DEST_DIR/$SCRIPT_NAME"; then
    chmod +x "$DEST_DIR/$SCRIPT_NAME"
    echo "Script downloaded and made executable."
else
    echo "Error: Script download failed. Check the URL and your internet connection."
    exit 1
fi

# 4. Create the service configuration (for daemontools)
echo "[3/6] Configuring the startup service..."
mkdir -p "$SERVICE_DIR"
cat <<EOF > "$SERVICE_DIR/run"
#!/bin/sh
# Execute the python script and pipe its output to the system logger
exec $DEST_DIR/$SCRIPT_NAME 2>&1 | logger -t $SERVICE_NAME
EOF
chmod +x "$SERVICE_DIR/run"
echo "Service configured."

# 5. Create the scripts for persistent startup (rc.local method)
echo "[4/6] Setting up persistent auto-start..."
# Script #1: The permanent setup script
cat <<'EOF' > /data/setup-services.sh
#!/bin/bash
echo "Executing setup-services.sh script..." | logger -t setup-services
sleep 20 # Wait for the system to be fully ready
SERVICE_NAME="dbus-mqtt-bridge"
# Create service link if it doesn't exist
if [ ! -L "/service/$SERVICE_NAME" ]; then
    if [ -d "/data/service/$SERVICE_NAME" ]; then
        ln -s "/data/service/$SERVICE_NAME" "/service/$SERVICE_NAME"
        echo "Service link for $SERVICE_NAME created." | logger -t setup-services
    fi
fi
# Re-enable rc.local for the next boot
if [ -f /data/rc.local.disabled ]; then
    mv /data/rc.local.disabled /data/rc.local
    echo "rc.local has been re-enabled for the next boot." | logger -t setup-services
fi
EOF
chmod +x /data/setup-services.sh

# Script #2: The one-shot trigger (rc.local)
cat <<'EOF' > /data/rc.local
#!/bin/bash
# This script will run our permanent setup script in the background.
/data/setup-services.sh &
EOF
chmod +x /data/rc.local
echo "Persistent auto-start configured."

# 6. Activate the service
echo "[5/6] Activating the service..."
if [ ! -L "/service/$SERVICE_NAME" ]; then
    ln -s "$SERVICE_DIR" "/service/$SERVICE_NAME"
fi
echo "Service activated."

echo "[6/6] Cleaning up and restarting the service to apply all changes..."
# Use -t to restart (terminate and then start) the service cleanly
svc -t /service/$SERVICE_NAME

echo "--- Installation Complete! ---"
echo
echo "The service is now running."
echo "To verify, wait about 30 seconds, then run this command:"
echo "svstat /service/dbus-mqtt-bridge"
echo "You should see a message starting with 'up'."
