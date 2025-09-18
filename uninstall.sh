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
# Remove the symlink to deactivate the service
if [ -L "$SERVICE_LINK" ]; then
    rm "$SERVICE_LINK"
    echo "Service link removed."
fi
# Wait a moment for the service manager to recognize the change
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

# 4. Clean up the auto-start configuration
echo "[3/4] Cleaning up auto-start configuration..."
if [ -f "$SETUP_SERVICES" ]; then
    rm "$SETUP_SERVICES"
    echo "Setup script ($SETUP_SERVICES) removed."
fi
if [ -f "$RC_LOCAL" ]; then
    # To be safe, only remove rc.local if it only contains our setup line.
    if grep -q "$SETUP_SERVICES" "$RC_LOCAL" && [ "$(wc -l < "$RC_LOCAL")" -le 3 ]; then
        rm "$RC_LOCAL"
        echo "Startup file ($RC_LOCAL) removed."
    else
        echo "WARNING: $RC_LOCAL appears to contain other custom modifications."
        echo "Please edit it manually and remove the line that runs: $SETUP_SERVICES"
    fi
fi

# 5. Remove logs (optional, but clean)
echo "[4/4] Removing logs..."
# The Venus OS logger for daemontools services does not create a separate log directory.
# Logs are sent to the main system log (/var/log/messages).
# There is nothing to safely remove here.
echo "No separate log files to remove."

echo "--- Uninstallation Complete! ---"
echo "The service and all its files have been removed."
echo "A reboot may be useful to finalize the cleanup."
