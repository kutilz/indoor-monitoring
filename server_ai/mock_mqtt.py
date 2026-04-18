"""
Mock MQTT untuk mode akuisisi — tidak membutuhkan broker atau koneksi jaringan.
Interface identik dengan MQTTClient sehingga main.py bisa swap tanpa
mengubah kode apapun.

Semua perintah relay dicatat ke console dan file CSV di data/logs/.
"""

import csv
import json
import os
from datetime import datetime
import config


class MockMQTTClient:
    """
    Simulator MQTT tanpa broker.
    Drop-in replacement untuk MQTTClient pada mode akuisisi.
    """

    def __init__(self):
        self._connected = True  # Selalu "terhubung" di mode ini
        self._log_path = os.path.join(
            config.LOG_DIR, config.LOG_COMMANDS_FILE
        )
        self._ensure_log_file()
        print("[MockMQTT] Mode Akuisisi — MQTT disimulasikan, "
              "tidak ada broker yang dibutuhkan.")
        print(f"[MockMQTT] Log perintah: {os.path.abspath(self._log_path)}")

    def _ensure_log_file(self):
        """Buat file CSV beserta header jika belum ada."""
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
        if not os.path.exists(self._log_path):
            with open(self._log_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "relay_num", "state", "topic", "payload"
                ])

    def connect(self):
        """Tidak melakukan apa-apa, langsung 'terhubung'."""
        print("[MockMQTT] connect() dipanggil — tidak ada operasi jaringan.")

    def disconnect(self):
        """Tidak melakukan apa-apa."""
        print("[MockMQTT] disconnect() dipanggil.")

    def publish_relay(self, relay_num: int, state: str):
        """
        Simulasikan pengiriman perintah relay.
        Catat ke console dan CSV.

        Args:
            relay_num: Nomor relay (1-4)
            state: "ON" atau "OFF"
        """
        topic = config.MQTT_TOPIC_RELAY
        payload = json.dumps({"relay": relay_num, "state": state})
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Warna terminal (opsional, diabaikan di terminal yang tidak support ANSI)
        color = "\033[92m" if state == "ON" else "\033[91m"
        reset = "\033[0m"
        relay_names = {
            config.RELAY_AC: "AC",
            config.RELAY_LIGHT_FRONT: "Lampu Depan",
            config.RELAY_LIGHT_BACK: "Lampu Belakang",
            config.RELAY_SPARE: "Spare",
        }
        name = relay_names.get(relay_num, f"Relay {relay_num}")

        print(f"[MockMQTT] {ts} | {color}{name:15s} → {state}{reset}")

        # Tulis ke CSV
        try:
            with open(self._log_path, "a", newline="",
                      encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([ts, relay_num, state, topic, payload])
        except IOError as e:
            print(f"[MockMQTT] Gagal menulis log: {e}")

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


def create_mqtt_client(mode: str):
    """
    Factory function — pilih klien MQTT berdasarkan mode.

    Args:
        mode: "akuisisi" → MockMQTTClient, "real" → MQTTClient

    Returns:
        Instance dengan interface publish_relay() dan publish_commands()
    """
    if mode == "akuisisi":
        return MockMQTTClient()
    elif mode == "real":
        from mqtt_client import MQTTClient
        return MQTTClient()
    else:
        raise ValueError(
            f"Mode tidak dikenal: '{mode}'. Gunakan 'akuisisi' atau 'real'."
        )
