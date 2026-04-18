"""
Wrapper Paho-MQTT untuk mode real.
Mengelola koneksi ke broker Mosquitto dan mempublikasikan
perintah relay ke ESP32.
"""

import json
import threading
import time
import paho.mqtt.client as mqtt
import config


class MQTTClient:
    """
    Klien MQTT dengan auto-reconnect dan publish thread-safe.

    Topik yang digunakan:
        classroom/relay  → payload: {"relay": <int>, "state": "ON"|"OFF"}
    """

    def __init__(self,
                 host: str = None,
                 port: int = None,
                 client_id: str = None):
        self._host = host or config.MQTT_BROKER_HOST
        self._port = port or config.MQTT_BROKER_PORT
        self._client_id = client_id or config.MQTT_CLIENT_ID

        self._connected = False
        self._lock = threading.Lock()

        self._client = mqtt.Client(client_id=self._client_id)
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_publish    = self._on_publish

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            print(f"[MQTT] Terhubung ke broker {self._host}:{self._port}")
        else:
            print(f"[MQTT] Gagal terhubung, kode: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            print(f"[MQTT] Koneksi terputus (rc={rc}). Reconnecting...")
            self._reconnect_loop()

    def _on_publish(self, client, userdata, mid):
        pass  # Bisa diaktifkan untuk debug verbose

    # ── Koneksi ────────────────────────────────────────────────────────────────

    def connect(self):
        """Hubungkan ke broker dan mulai network loop di background."""
        print(f"[MQTT] Menghubungkan ke {self._host}:{self._port}...")
        self._client.connect(
            self._host, self._port, config.MQTT_KEEPALIVE
        )
        self._client.loop_start()

        # Tunggu konfirmasi koneksi maksimal 10 detik
        deadline = time.time() + 10
        while not self._connected and time.time() < deadline:
            time.sleep(0.1)

        if not self._connected:
            raise ConnectionError(
                f"Tidak dapat terhubung ke broker MQTT di "
                f"{self._host}:{self._port}\n"
                "Pastikan Mosquitto sudah berjalan."
            )

    def disconnect(self):
        """Putuskan koneksi dengan bersih."""
        self._client.loop_stop()
        self._client.disconnect()
        print("[MQTT] Koneksi ditutup.")

    def _reconnect_loop(self, interval: float = 5.0):
        """Coba reconnect di background thread."""
        def _loop():
            while not self._connected:
                try:
                    print(f"[MQTT] Mencoba reconnect ke "
                          f"{self._host}:{self._port}...")
                    self._client.reconnect()
                    time.sleep(interval)
                except Exception as e:
                    print(f"[MQTT] Reconnect gagal: {e}")
                    time.sleep(interval)

        thread = threading.Thread(target=_loop, daemon=True)
        thread.start()

    # ── Publish ────────────────────────────────────────────────────────────────

    def publish_relay(self, relay_num: int, state: str):
        """
        Kirim perintah ke relay ESP32.

        Args:
            relay_num: Nomor relay (1-4)
            state: "ON" atau "OFF"
        """
        if not self._connected:
            print(f"[MQTT] Tidak terhubung — perintah relay {relay_num} "
                  f"{state} diabaikan.")
            return

        payload = json.dumps({"relay": relay_num, "state": state})
        topic = config.MQTT_TOPIC_RELAY

        with self._lock:
            result = self._client.publish(topic, payload, qos=1)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[MQTT] Publish → {topic}: {payload}")
        else:
            print(f"[MQTT] Gagal publish (rc={result.rc}): {payload}")

    def publish_commands(self, commands: list[dict]):
        """
        Publish daftar perintah relay sekaligus.

        Args:
            commands: Output dari ControlLogic.get_relay_commands()
        """
        for cmd in commands:
            self.publish_relay(cmd["relay"], cmd["state"])

    @property
    def is_connected(self) -> bool:
        return self._connected
