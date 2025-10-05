#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Variables ---
SERVICE_NAME="dbus-mqtt-bridge"
SCRIPT_DIR="/data/$SERVICE_NAME"
SERVICE_DIR="/data/service/$SERVICE_NAME"
SERVICE_LINK="/service/$SERVICE_NAME"
RC_LOCAL="/data/rc.local"
SETUP_SERVICES="/data/setup-services.sh"

# --- Start of Script ---
echo "--- Starting D-Bus to MQTT Bridge Service Uninstallation ---"

# 1. Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as the root user."
    exit 1
fi

# 2. Stop and disable the service
echo "[1/4] Stopping and disabling the service..."
if [ -L "$SERVICE_LINK" ]; then
    rm "$SERVICE_LINK"
    echo "Service link removed."
fi
sleep 2

# 3. Remove the main script and service files
echo "[2/4] Removing program files..."
if [ -d "$SCRIPT_DIR" ]; then
    rm -rf "$SCRIPT_DIR"
    echo "Program directory ($SCRIPT_DIR) removed."
fi
if [ -d "$SERVICE_DIR" ]; then
    rm -rf "$SERVICE_DIR"
    echo "Service directory ($SERVICE_DIR) removed."
fi

# 4. Clean up the auto-start configuration (SAFE METHOD)
echo "[3/4] Cleaning up auto-start configuration..."
# First, safely remove our permanent setup script.
if [ -f "$SETUP_SERVICES" ]; then
    rm "$SETUP_SERVICES"
    echo "Setup script ($SETUP_SERVICES) removed."
fi

# --- MODIFICA CHIAVE: Rimozione sicura della riga da rc.local ---
# Now, carefully edit rc.local to remove ONLY our startup line.
# This prevents breaking other custom scripts.
if [ -f "$RC_LOCAL" ]; then
    # Use sed to perform an in-place deletion ('-i') of any line ('d')
    # containing the name of our setup script.
    sed -i '/setup-services.sh/d' "$RC_LOCAL"
    echo "Startup entry safely removed from $RC_LOCAL."
fi
# --- FINE MODIFICA ---

# 5. Remove logs
echo "[4/4] Removing logs..."
# The service uses a dedicated log directory managed by multilog.
if [ -d "/var/log/$SERVICE_NAME" ]; then
    rm -rf "/var/log/$SERVICE_NAME"
    echo "Log directory (/var/log/$SERVICE_NAME) removed."
fi

echo "--- Uninstallation Complete! ---"
echo "The service and all its files have been removed."
echo "A reboot may be useful to finalize the cleanup."
