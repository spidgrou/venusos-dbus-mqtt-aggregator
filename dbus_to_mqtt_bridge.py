#!/usr/bin/env python3

import sys, os, platform, logging, time, dbus
from gi.repository import GLib
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import threading

# --- Config ---
MQTT_BROKER_ADDRESS = "127.0.0.1"
MQTT_BROKER_PORT = 1883
UPDATE_INTERVAL_SECONDS = 5
RESCAN_INTERVAL_SECONDS = 60
# --- End Config ---

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DbusMqttBridge:
    VEBUS_STATE_MAP = {
        0: 'Off', 1: 'Low Power', 2: 'Fault', 3: 'Bulk', 4: 'Absorption',
        5: 'Float', 6: 'Storage', 7: 'Equalize', 8: 'Passthru',
        9: 'Inverting', 10: 'Power assist', 11: 'Power supply', 252: 'External Control'
    }

    def __init__(self):
        logging.info("Waiting 15 seconds for all services to start...")
        time.sleep(15)
        self._dbus_conn = dbus.SystemBus()
        self._dbus_paths = {
            'system': {'service': 'com.victronenergy.system'}, 'settings': {'service': 'com.victronenergy.settings'},
            'battery': {'service': None}, 'solarchargers': [], 'vebus': {'service': None}
        }
        self.system_id = None; self.data = {}
        logging.info("Starting D-Bus to MQTT bridge service")
        self._find_services()
        self.system_id = self._dbus_get_value(self._dbus_paths['settings']['service'], "/Settings/System/VrmPortalId")
        if not self.system_id:
            logging.warning("VRM Portal ID not found. Falling back to device serial.")
            self.system_id = self._dbus_get_value(self._dbus_paths['system']['service'], "/Serial")
        if not self.system_id:
            logging.error("Could not get a unique ID for the system. Exiting."); sys.exit(1)
        logging.info(f"System ID for MQTT topics: {self.system_id}")
        self.mqtt_client = mqtt.Client(CallbackAPIVersion.VERSION1, client_id=f"DbusMqttBridge-{os.getpid()}")
        self.mqtt_client.on_connect = self._on_mqtt_connect; self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        try:
            self.mqtt_client.connect(MQTT_BROKER_ADDRESS, MQTT_BROKER_PORT, 60)
            threading.Thread(target=self.mqtt_client.loop_forever, daemon=True).start()
        except Exception as e:
            logging.error(f"MQTT connection error: {e}"); sys.exit(1)

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0: logging.info("Successfully connected to MQTT broker")
        else: logging.error(f"MQTT connection failed with code: {rc}")
    def _on_mqtt_disconnect(self, client, userdata, rc):
        logging.warning(f"Disconnected from MQTT. Code: {rc}")
    def _dbus_get_value(self, service, path, default=None):
        try: return self._dbus_conn.get_object(service, path).GetValue()
        except: return default
    def _get_display_name(self, service):
        custom_name = self._dbus_get_value(service, '/CustomName')
        return custom_name if custom_name else self._dbus_get_value(service, '/ProductName', default=service)

    def _find_services(self, is_rescan=False):
        bus_object = self._dbus_conn.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus")
        service_names = bus_object.ListNames(dbus_interface="org.freedesktop.DBus")
        known_chargers = [c['service'] for c in self._dbus_paths['solarchargers']]
        for service in service_names:
            service = str(service)
            if service.startswith('com.victronenergy.battery') and not self._dbus_paths['battery']['service']:
                self._dbus_paths['battery']['service'] = service; logging.info(f"Found Battery: '{self._get_display_name(service)}' ({service.split('.')[-1]})")
            elif service.startswith('com.victronenergy.solarcharger') and service not in known_chargers:
                self._dbus_paths['solarchargers'].append({'service': service}); log_prefix = "Detected new Solar Charger:" if is_rescan else "Found Solar Charger:"; logging.info(f"{log_prefix} '{self._get_display_name(service)}' ({service.split('.')[-1]})")
            elif service.startswith('com.victronenergy.vebus') and not self._dbus_paths['vebus']['service']:
                self._dbus_paths['vebus']['service'] = service; log_prefix = "Detected new VE.Bus device:" if is_rescan else "Found VE.Bus device:"; logging.info(f"{log_prefix} '{self._get_display_name(service)}' ({service.split('.')[-1]})")
        if not is_rescan:
            if not self._dbus_paths['battery']['service']: logging.warning("WARNING: No battery monitor found.")
            if not self._dbus_paths['solarchargers']: logging.warning("WARNING: No solar chargers found.")
            if not self._dbus_paths['vebus']['service']: logging.warning("WARNING: No VE.Bus device (MultiPlus) found.")

    def rescan_for_new_devices(self):
        logging.info("Performing periodic device scan...")
        self._find_services(is_rescan=True)
        return True
    
    def _update_data(self):
        bat_service = self._dbus_paths['battery']['service']
        if bat_service: self.data['battery_current'] = self._dbus_get_value(bat_service, '/Dc/0/Current'); self.data['battery_power'] = self._dbus_get_value(bat_service, '/Dc/0/Power'); self.data['battery_voltage'] = self._dbus_get_value(bat_service, '/Dc/0/Voltage'); self.data['battery_soc'] = self._dbus_get_value(bat_service, '/Soc'); self.data['battery_consumed_ah'] = self._dbus_get_value(bat_service, '/ConsumedAmphours'); self.data['battery_aux_voltage'] = self._dbus_get_value(bat_service, '/Dc/1/Voltage')
        sys_service = self._dbus_paths['system']['service']
        if sys_service: self.data['solar_power'] = self._dbus_get_value(sys_service, '/Dc/Pv/Power'); self.data['solar_current'] = self._dbus_get_value(sys_service, '/Dc/Pv/Current')
        total_yield = 0.0
        for charger in self._dbus_paths['solarchargers']:
            yield_kwh = self._dbus_get_value(charger['service'], '/History/Daily/0/Yield')
            if yield_kwh is not None: total_yield += (yield_kwh * 1000)
        self.data['solar_yield_today_wh'] = total_yield
        vebus_service = self._dbus_paths['vebus']['service']
        if vebus_service:
            self.data['vebus_in_voltage'] = self._dbus_get_value(vebus_service, '/Ac/ActiveIn/L1/V'); self.data['vebus_in_frequency'] = self._dbus_get_value(vebus_service, '/Ac/ActiveIn/L1/F'); self.data['vebus_in_power'] = self._dbus_get_value(vebus_service, '/Ac/ActiveIn/L1/P')
            self.data['vebus_out_voltage'] = self._dbus_get_value(vebus_service, '/Ac/Out/L1/V'); self.data['vebus_out_frequency'] = self._dbus_get_value(vebus_service, '/Ac/Out/L1/F'); self.data['vebus_out_power'] = self._dbus_get_value(vebus_service, '/Ac/Out/L1/P')
            self.data['vebus_charge_current'] = self._dbus_get_value(vebus_service, '/Dc/0/Current')
            state_code = self._dbus_get_value(vebus_service, '/State')
            if state_code is not None: self.data['vebus_state_text'] = self.VEBUS_STATE_MAP.get(state_code, f'Unknown ({state_code})')
        return True
    
    def _publish_to_mqtt(self):
        if not self.mqtt_client.is_connected(): return
        topic_map = {
            'battery_current': 'batteryMonitor/Current', 'battery_power': 'batteryMonitor/Power', 'battery_voltage': 'batteryMonitor/Voltage', 'battery_soc': 'batteryMonitor/SOC',
            'battery_consumed_ah': 'batteryMonitor/UsedAh', 'battery_aux_voltage': 'batteryMonitor/VoltageAUX',
            'solar_power': 'solar/totalPower', 'solar_current': 'solar/totalCurrent', 'solar_yield_today_wh': 'solar/yieldTodayWh',
            'vebus_in_voltage':   'AC/IN/Voltage', 'vebus_in_frequency': 'AC/IN/Frequency', 'vebus_in_power':     'AC/IN/Power',
            'vebus_out_voltage':   'AC/OUT/Voltage', 'vebus_out_frequency': 'AC/OUT/Frequency', 'vebus_out_power':     'AC/OUT/Power',
            'vebus_charge_current': 'AC/CHARGER/Current', 'vebus_state_text': 'AC/CHARGER/State'
        }
        for key, topic_suffix in topic_map.items():
            value = self.data.get(key)
            if value is not None:
                topic = f"Y/{topic_suffix}"
                payload = round(value, 2) if isinstance(value, (int, float)) else value
                self.mqtt_client.publish(topic, payload, retain=True)

    def run(self):
        self._update_data(); self._publish_to_mqtt()
        self.mqtt_client.publish(f"R/{self.system_id}/system/0/Serial", self.system_id, retain=True)
        self.mqtt_client.publish(f"Y/serial", self.system_id, retain=True)
        return True

if __name__ == "__main__":
    bridge = DbusMqttBridge()
    GLib.timeout_add_seconds(UPDATE_INTERVAL_SECONDS, bridge.run)
    GLib.timeout_add_seconds(RESCAN_INTERVAL_SECONDS, bridge.rescan_for_new_devices)
    logging.info("Starting main loop.")
    mainloop = GLib.MainLoop()
    mainloop.run()
