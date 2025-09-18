--- Starting D-Bus to MQTT Bridge Service Installation ---
[1/6] Installing dependencies (python3-paho-mqtt)...
Dependencies installed.
[2/6] Creating directory and downloading the main script...
Script downloaded and made executable.
[3/6] Configuring the startup service...
Service configured.
[4/6] Setting up persistent auto-start...
Persistent auto-start configured.
[5/6] Activating the service...
Service activated.
[6/6] Cleaning up and restarting the service to apply all changes...
svc: warning: unable to control /service/dbus-mqtt-bridge: file does not exist
--- Installation Complete! ---

The service is now running.
To verify, wait about 30 seconds, then run this command:
svstat /service/dbus-mqtt-bridge
You should see a message starting with 'up'.
root@cerbosgx:~# svstat /service/dbus-mqtt-bridge
/service/dbus-mqtt-bridge: up (pid 2604) 7 seconds
root@cerbosgx:~#
