# D-Bus to MQTT Aggregator & Bridge for Victron Venus OS

This project provides a lightweight and efficient Python script that acts as a bridge between the internal D-Bus system of a Victron device (like a Cerbo GX) and an MQTT broker.

It was created as a high-performance alternative to Node-RED to reduce resource consumption (especially RAM) and provide a stable, reboot-proof service.

## Main Features

*   **Automatic Discovery:** Dynamically detects present devices, including:
    *   Battery Monitors (BMV, SmartShunt)
    *   Solar Chargers (MPPTs)
    *   Inverter/Chargers (MultiPlus, Quattro)
*   **Comprehensive Data Reading:** Reads and publishes the most important data points, including:
    *   **Battery:** Voltage, Current, Power, State of Charge (SOC), Auxiliary Voltage, Consumed Ah.
    *   **Solar:** Total Power and Current, Daily Energy Yield (in Wh).
    *   **MultiPlus:** AC In/Out data (Voltage, Power, Frequency), Charge Current, and Operating State (Bulk, Inverting, Passthru, etc.).
*   **Dynamic MQTT Topics:** Creates a main topic based on the device's unique serial number, making the script portable to any Cerbo GX.
*   **Stable and Lightweight:** Designed for very low CPU and RAM consumption.
*   **Automatic Startup:** Thanks to a robust startup system, the service starts automatically on every reboot.

<img width="327" height="360" alt="image" src="https://github.com/user-attachments/assets/f84de9e7-20c4-414a-8b3c-79f4327dfe51" />


## Prerequisites

Before you begin, ensure you have:

1.  **SSH access** to your Cerbo GX. You can enable it from the menu: `Settings -> Services -> SSH on LAN`.
2.  The **IP address** of your Cerbo GX.
3.  A recent version of the Venus OS firmware (v2.80+ recommended).
4.  The **"All modifications enabled"** option turned ON if you are using a recent firmware version (v3.40+). This can be found under `Settings -> General`.

## Easy Installation

Installation has been made as simple as possible. You only need to run a single command on your Cerbo.

1.  Connect to your Cerbo GX via SSH.
2.  Copy the entire command below, paste it into the terminal, and press Enter. The script will handle everything else automatically.

```bash
curl -sSL https://raw.githubusercontent.com/spidgrou/venusos-dbus-mqtt-aggregator/main/install.sh | bash
```
The installation script will take care of everything:
*   Installing necessary dependencies.
*   Downloading the main program.
*   Configuring it as a permanent, auto-starting service.
*   Starting the service.

## How to Verify it's Working

After the installation finishes, wait about 30 seconds to allow the service to start completely. Then, run the following commands to check its status.

#### 1. Check the Service Status

This is the most important command. It tells you if the program is running.
```bash
svstat /service/dbus-mqtt-bridge
```
**Expected output:** You should see a message beginning with `up`, like this:
```
/service/dbus-mqtt-bridge: up (pid 1234) 45 seconds
```

#### 2. Check the Logs (if something is wrong)

If you want to see the startup messages or diagnose any issues, you can view the logs:
```bash
tail -f /var/log/messages | grep dbus-mqtt-bridge
```

## Configuration

Out-of-the-box, the script is configured to connect to an MQTT broker running on the Cerbo itself (`127.0.0.1`). If your broker is on a different machine, you can easily change the address.

1.  Open the script file with a text editor:
    ```bash
    nano /data/dbus-mqtt-bridge/dbus_to_mqtt_bridge.py
    ```
2.  Find and modify the line `MQTT_BROKER_ADDRESS = "127.0.0.1"`.
3.  Save the file (`Ctrl+O`, then Enter) and exit (`Ctrl+X`).
4.  Restart the service to apply the changes:
    ```bash
    svc -t /service/dbus-mqtt-bridge
    ```

---

## Uninstallation

If you wish to completely remove the service from your device, you can do so with a single command. This will stop the service, delete all its files, and remove the auto-start configuration.

1.  Connect to your Cerbo GX via SSH.
2.  Copy and paste the entire command below and press Enter.

```bash
curl -sSL https://raw.githubusercontent.com/spidgrou/venusos-dbus-mqtt-aggregator/main/uninstall.sh | bash
```

The uninstallation is safe and will only remove the files created by this project.
