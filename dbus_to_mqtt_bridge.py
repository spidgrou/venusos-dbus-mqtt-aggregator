#!/usr/bin/env python3

import sys, os, platform, logging, time, dbus, traceback, signal
from gi.repository import GLib
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
from dbus.types import Array as dbusArray, Int16 as dbusInt16, UInt16 as dbusUInt16, \
    Int32 as dbusInt32, UInt32 as dbusUInt32, Double as dbusDouble, String as dbusString, \
    Byte as dbusByte

# --- Config ---
MQTT_BROKER_ADDRESS = "127.0.0.1"
MQTT_BROKER_PORT = 1883
UPDATE_INTERVAL_SECONDS = 5
RESCAN_INTERVAL_SECONDS = 60
DBUS_WAIT_TIMEOUT = 30  # max secondi di attesa per servizi D-Bus all'avvio
MQTT_RETRY_SECONDS = 5  # intervallo tra tentativi di riconnessione MQTT
# --- End Config ---

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class DbusMqttBridge:
    VEBUS_STATE_MAP = {
        0: 'Off', 1: 'Low Power', 2: 'Fault', 3: 'Bulk', 4: 'Absorption',
        5: 'Float', 6: 'Storage', 7: 'Equalize', 8: 'Passthru',
        9: 'Inverting', 10: 'Power assist', 11: 'Power supply', 252: 'External Control'
    }

    def __init__(self):
        logging.info("--- EXECUTING SCRIPT VERSION 18.0 ---")

        self._dbus_conn = dbus.SystemBus()
        self._dbus_paths = {
            'system': {'service': 'com.victronenergy.system'},
            'settings': {'service': 'com.victronenergy.settings'},
            'battery': {'service': None},
            'solarchargers': [],
            'vebus': {'service': None}
        }
        self.system_id = None
        self.data = {}
        self._mqtt_connected = False
        self._socket_watch = None
        self._socket_timer = None
        self._shutdown = False
        self._mainloop = None

        logging.info("Starting D-Bus to MQTT bridge service")

        # --- Attesa attiva D-Bus (invece di sleep(15) bloccante) ---
        self._wait_for_dbus()

        self._find_services()

        # --- System ID (come prima) ---
        self.system_id = self._get_dbus_value(
            self._dbus_paths['settings']['service'], "/Settings/System/VrmPortalId"
        )
        if not self.system_id:
            logging.warning("VRM Portal ID not found. Falling back to device serial.")
            self.system_id = self._get_dbus_value(
                self._dbus_paths['system']['service'], "/Serial"
            )
        if not self.system_id:
            logging.error("Could not get a unique ID for the system. Exiting.")
            sys.exit(1)
        logging.info(f"System ID for MQTT topics: {self.system_id}")

        # --- MQTT setup integrato con GLib ---
        self._setup_mqtt()

    # ================================================================
    # ATTESA ATTIVA D-BUS
    # ================================================================

    def _wait_for_dbus(self):
        """Invece di sleep(15) fisso, poll ogni secondo finché il
        servizio system non è disponibile, con timeout configurabile."""
        logging.info(f"Waiting for D-Bus services (timeout: {DBUS_WAIT_TIMEOUT}s)...")
        start = time.time()
        while time.time() - start < DBUS_WAIT_TIMEOUT:
            try:
                self._dbus_conn.get_object(
                    'com.victronenergy.system', '/Serial'
                ).GetValue()
                logging.info("D-Bus services ready.")
                return
            except Exception:
                time.sleep(1)
        logging.warning(
            f"D-Bus services not ready after {DBUS_WAIT_TIMEOUT}s, "
            "continuing anyway."
        )

    # ================================================================
    # MQTT — INTEGRATO CON GLib MAIN LOOP
    # ================================================================

    def _setup_mqtt(self):
        self.mqtt_client = mqtt.Client(
            CallbackAPIVersion.VERSION1,
            client_id=f"DbusMqttBridge-{os.getpid()}"
        )
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect

        # Last Will & Testament: pubblicato automaticamente dal broker
        # se la connessione cade in modo improvviso
        self.mqtt_client.will_set("Y/online", "0", retain=True)

        self._init_mqtt()

    def _init_mqtt(self):
        """Tentativo di connessione MQTT. Se fallisce, schedule retry."""
        try:
            logging.info("Connecting to MQTT broker...")
            self.mqtt_client.connect(MQTT_BROKER_ADDRESS, MQTT_BROKER_PORT, 60)
            self._setup_socket_handlers()
            return False  # stop retry se chiamato da GLib timeout
        except Exception as e:
            logging.error(f"MQTT connection failed: {e}, retrying in {MQTT_RETRY_SECONDS}s")
            # schedule retry
            GLib.timeout_add_seconds(MQTT_RETRY_SECONDS, self._init_mqtt)
            return False  # GLib timeout single-shot

    def _setup_socket_handlers(self):
        """Integra il socket MQTT nel GLib main loop (pattern Victron)."""
        # Rimuovi watch precedente se esiste
        if self._socket_watch is not None:
            GLib.source_remove(self._socket_watch)
            self._socket_watch = None

        try:
            sock = self.mqtt_client.socket()
            self._socket_watch = GLib.io_add_watch(
                sock.fileno(), GLib.IO_IN,
                self._on_mqtt_socket_in
            )
        except Exception as e:
            logging.warning(f"Cannot setup MQTT socket watch: {e}")
            return

        # Timer per loop_misc + loop_write (1 volta al secondo)
        if self._socket_timer is None:
            self._socket_timer = GLib.timeout_add_seconds(
                1, self._on_mqtt_socket_timer
            )

        logging.info("MQTT socket handlers installed in GLib main loop.")

    def _on_mqtt_socket_in(self, source, condition):
        """Chiamato da GLib quando il socket MQTT ha dati da leggere."""
        try:
            self.mqtt_client.loop_read()
        except Exception:
            logging.error("MQTT loop_read error:\n" + traceback.format_exc())
        return True  # keep watch alive

    def _on_mqtt_socket_timer(self):
        try:
            self.mqtt_client.loop_misc()
            if self.mqtt_client.is_connected():
                while self.mqtt_client.want_write():
                    rc = self.mqtt_client.loop_write()
                    if rc != mqtt.MQTT_ERR_SUCCESS:
                        break
        except Exception:
            logging.error("MQTT timer error:\n" + traceback.format_exc())
        return True  # keep timer alive

    # --- Callback MQTT ---

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._mqtt_connected = True
            logging.info("Successfully connected to MQTT broker.")
            # Pubblica online state
            self.mqtt_client.publish("Y/online", "1", retain=True)
            # Alla riconnessione, ripubblica i valori correnti
            if self.data:
                self._publish_to_mqtt()
                self.mqtt_client.publish(
                    f"R/{self.system_id}/system/0/Serial", self.system_id, retain=True
                )
                self.mqtt_client.publish("Y/serial", self.system_id, retain=True)
                logging.info("Re-published current values after reconnect.")
        else:
            logging.error(f"MQTT connection failed with code: {rc}")

    def _on_mqtt_disconnect(self, client, userdata, rc):
        self._mqtt_connected = False
        logging.warning(f"Disconnected from MQTT. Code: {rc}")

        # Pubblica offline (in caso di disconnect pulito)
        try:
            self.mqtt_client.publish("Y/online", "0", retain=True)
        except Exception:
            pass

        # Rimuovi socket watch
        if self._socket_watch is not None:
            GLib.source_remove(self._socket_watch)
            self._socket_watch = None

        # Schedule riconnessione (solo se non siamo in shutdown)
        if not self._shutdown:
            logging.info(f"Reconnecting in {MQTT_RETRY_SECONDS}s...")
            GLib.timeout_add_seconds(MQTT_RETRY_SECONDS, self._reconnect_mqtt)

    def _reconnect_mqtt(self):
        """Tentativo di riconnessione. Se fallisce, GLib ritenta."""
        if self._shutdown:
            return False
        try:
            logging.info("Attempting MQTT reconnect...")
            self.mqtt_client.reconnect()
            self._setup_socket_handlers()
            logging.info("MQTT reconnect successful.")
            return False  # stop retry
        except Exception as e:
            logging.error(f"MQTT reconnect failed: {e}")
            return True  # GLib ritenta

    # ================================================================
    # D-BUS — (identico alla versione 17.2)
    # ================================================================

    def _get_dbus_value(self, service, path, default=None):
        try:
            val = self._dbus_conn.get_object(service, path).GetValue()
            if val is None:
                return default
            if isinstance(val, (int, float, str)):
                return val
            if isinstance(val, (dbusInt16, dbusUInt16, dbusInt32, dbusUInt32, dbusByte)):
                return int(val)
            if isinstance(val, (dbusDouble,)):
                return float(val)
            if isinstance(val, (dbusString,)):
                return str(val)
            if isinstance(val, (dbusArray, list)):
                return default
            return default
        except Exception:
            return default

    def _get_display_name(self, service):
        return self._get_dbus_value(
            service, '/CustomName',
            default=self._get_dbus_value(service, '/ProductName', default=service)
        )

    def _find_services(self, is_rescan=False):
        bus_object = self._dbus_conn.get_object(
            "org.freedesktop.DBus", "/org/freedesktop/DBus"
        )
        service_names = bus_object.ListNames(dbus_interface="org.freedesktop.DBus")
        known_chargers = [c['service'] for c in self._dbus_paths['solarchargers']]
        for service in service_names:
            service = str(service)
            if service.startswith('com.victronenergy.battery') \
                    and not self._dbus_paths['battery']['service']:
                self._dbus_paths['battery']['service'] = service
                logging.info(
                    f"Found Battery: '{self._get_display_name(service)}' "
                    f"({service.split('.')[-1]})"
                )
            elif service.startswith('com.victronenergy.solarcharger') \
                    and service not in known_chargers:
                self._dbus_paths['solarchargers'].append({'service': service})
                log_prefix = "Detected new Solar Charger:" \
                    if is_rescan else "Found Solar Charger:"
                logging.info(
                    f"{log_prefix} '{self._get_display_name(service)}' "
                    f"({service.split('.')[-1]})"
                )
            elif service.startswith('com.victronenergy.vebus') \
                    and not self._dbus_paths['vebus']['service']:
                self._dbus_paths['vebus']['service'] = service
                log_prefix = "Detected new VE.Bus device:" \
                    if is_rescan else "Found VE.Bus device:"
                logging.info(
                    f"{log_prefix} '{self._get_display_name(service)}' "
                    f"({service.split('.')[-1]})"
                )
        if not is_rescan:
            if not self._dbus_paths['battery']['service']:
                logging.warning("WARNING: No battery monitor found.")
            if not self._dbus_paths['solarchargers']:
                logging.warning("WARNING: No solar chargers found.")
            if not self._dbus_paths['vebus']['service']:
                logging.warning("WARNING: No VE.Bus device (MultiPlus) found.")

    def rescan_for_new_devices(self):
        logging.info("--> Performing periodic device scan...")
        self._find_services(is_rescan=True)
        return True

    def _update_data(self):
        bat_service = self._dbus_paths['battery']['service']
        if bat_service:
            self.data['battery_current'] = self._get_dbus_value(
                bat_service, '/Dc/0/Current'
            )
            self.data['battery_power'] = self._get_dbus_value(
                bat_service, '/Dc/0/Power'
            )
            self.data['battery_voltage'] = self._get_dbus_value(
                bat_service, '/Dc/0/Voltage'
            )
            self.data['battery_soc'] = self._get_dbus_value(
                bat_service, '/Soc'
            )
            self.data['battery_consumed_ah'] = self._get_dbus_value(
                bat_service, '/ConsumedAmphours'
            )
            self.data['battery_aux_voltage'] = self._get_dbus_value(
                bat_service, '/Dc/1/Voltage'
            )

        sys_service = self._dbus_paths['system']['service']
        if sys_service:
            self.data['solar_power'] = self._get_dbus_value(
                sys_service, '/Dc/Pv/Power'
            )
            self.data['solar_current'] = self._get_dbus_value(
                sys_service, '/Dc/Pv/Current'
            )

        total_yield = 0.0
        for charger in self._dbus_paths['solarchargers']:
            yield_kwh = self._get_dbus_value(
                charger['service'], '/History/Daily/0/Yield'
            )
            if yield_kwh is not None:
                total_yield += (yield_kwh * 1000)
        self.data['solar_yield_today_wh'] = total_yield

        vebus_service = self._dbus_paths['vebus']['service']
        if vebus_service:
            self.data['vebus_in_voltage'] = self._get_dbus_value(
                vebus_service, '/Ac/ActiveIn/L1/V'
            )
            self.data['vebus_in_frequency'] = self._get_dbus_value(
                vebus_service, '/Ac/ActiveIn/L1/F'
            )
            self.data['vebus_in_power'] = self._get_dbus_value(
                vebus_service, '/Ac/ActiveIn/L1/P'
            )
            self.data['vebus_out_voltage'] = self._get_dbus_value(
                vebus_service, '/Ac/Out/L1/V'
            )
            self.data['vebus_out_frequency'] = self._get_dbus_value(
                vebus_service, '/Ac/Out/L1/F'
            )
            self.data['vebus_out_power'] = self._get_dbus_value(
                vebus_service, '/Ac/Out/L1/P'
            )
            self.data['vebus_charge_current'] = self._get_dbus_value(
                vebus_service, '/Dc/0/Current'
            )
            state_code = self._get_dbus_value(vebus_service, '/State')
            if state_code is not None:
                self.data['vebus_state_text'] = self.VEBUS_STATE_MAP.get(
                    state_code, f'Unknown ({state_code})'
                )

    def _publish_to_mqtt(self):
        if not self._mqtt_connected:
            logging.warning("MQTT not connected, skipping publication.")
            return
        topic_map = {
            'battery_current': 'batteryMonitor/Current',
            'battery_power': 'batteryMonitor/Power',
            'battery_voltage': 'batteryMonitor/Voltage',
            'battery_soc': 'batteryMonitor/SOC',
            'battery_consumed_ah': 'batteryMonitor/UsedAh',
            'battery_aux_voltage': 'batteryMonitor/VoltageAUX',
            'solar_power': 'solar/totalPower',
            'solar_current': 'solar/totalCurrent',
            'solar_yield_today_wh': 'solar/yieldTodayWh',
            'vebus_in_voltage': 'AC/IN/Voltage',
            'vebus_in_frequency': 'AC/IN/Frequency',
            'vebus_in_power': 'AC/IN/Power',
            'vebus_out_voltage': 'AC/OUT/Voltage',
            'vebus_out_frequency': 'AC/OUT/Frequency',
            'vebus_out_power': 'AC/OUT/Power',
            'vebus_charge_current': 'AC/CHARGER/Current',
            'vebus_state_text': 'AC/CHARGER/State',
        }
        for key, topic_suffix in topic_map.items():
            value = self.data.get(key)
            if value is not None:
                topic = f"Y/{topic_suffix}"
                payload = round(value, 2) if isinstance(value, (int, float)) else value
                self.mqtt_client.publish(topic, payload, retain=True)

    def _run_tick(self):
        """Chiamato da GLib ogni UPDATE_INTERVAL_SECONDS."""
        try:
            logging.debug("--> Main loop tick: Updating data and publishing...")
            self._update_data()
            self._publish_to_mqtt()
            if self._mqtt_connected:
                self.mqtt_client.publish(
                    f"R/{self.system_id}/system/0/Serial",
                    self.system_id, retain=True
                )
                self.mqtt_client.publish("Y/serial", self.system_id, retain=True)
        except Exception:
            logging.error("!!! UNHANDLED EXCEPTION IN MAIN LOOP:")
            logging.error(traceback.format_exc())
        return True  # keep GLib timer alive

    # ================================================================
    # GRACEFUL SHUTDOWN
    # ================================================================

    def _handle_sigterm(self, signum, frame):
        """Gestisce SIGTERM/SIGINT: pubblica offline e chiude pulitamente."""
        sig_name = signal.Signals(signum).name
        logging.info(f"Received {sig_name}, initiating graceful shutdown...")
        self._shutdown = True

        if self._mqtt_connected:
            try:
                # Pubblica offline state
                self.mqtt_client.publish("Y/online", "0", retain=True)
                self.mqtt_client.loop_misc()
                while self.mqtt_client.want_write():
                    self.mqtt_client.loop_write(100)
            except Exception:
                pass

        try:
            self.mqtt_client.disconnect()
        except Exception:
            pass

        if self._socket_watch is not None:
            GLib.source_remove(self._socket_watch)
        if self._socket_timer is not None:
            GLib.source_remove(self._socket_timer)

        if self._mainloop is not None:
            self._mainloop.quit()

        logging.info("Shutdown complete.")


# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    bridge = DbusMqttBridge()

    # Catch SIGTERM/SIGINT per graceful shutdown
    signal.signal(signal.SIGTERM, bridge._handle_sigterm)
    signal.signal(signal.SIGINT, bridge._handle_sigterm)

    # Schedule periodic tasks
    GLib.timeout_add_seconds(UPDATE_INTERVAL_SECONDS, bridge._run_tick)
    GLib.timeout_add_seconds(RESCAN_INTERVAL_SECONDS, bridge.rescan_for_new_devices)

    logging.info("Starting main loop.")
    bridge._mainloop = GLib.MainLoop()
    bridge._mainloop.run()
