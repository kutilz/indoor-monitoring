"""
HTTP client untuk node aktuator (D1 Mini / ESP32).
Berkomunikasi dengan firmware d1mini_actuator.ino via REST API.

Semua method mengembalikan False / dict kosong jika node offline — tidak crash.
Timeout singkat (2 detik default) agar tidak memblock main loop deteksi.
"""

import requests
import config


class ActuatorClient:
    """
    Client HTTP untuk node aktuator.
    Endpoint yang tersedia di firmware:
        GET  /health
        GET  /sensor
        GET  /servo/config
        POST /servo/move?id=<0-2>&angle=<0-180>
        POST /servo/click?id=<0-2>
        POST /servo/calibrate?id=<0-2>&stay=<angle>&click=<angle>
        POST /relay?state=<ON|OFF>
    """

    def __init__(self, base_url: str = None, timeout: int = None):
        self._base_url = (base_url or config.ACTUATOR_URL).rstrip("/")
        self._timeout  = timeout or config.ACTUATOR_TIMEOUT
        self._online   = False

    # ── Konektivitas ──────────────────────────────────────────────────────────

    def is_online(self) -> bool:
        """Cek apakah node aktuator bisa dihubungi."""
        try:
            r = requests.get(f"{self._base_url}/health",
                             timeout=self._timeout)
            self._online = (r.status_code == 200)
        except Exception:
            self._online = False
        return self._online

    @property
    def online(self) -> bool:
        return self._online

    # ── Sensor ───────────────────────────────────────────────────────────────

    def get_sensor(self) -> dict:
        """
        Ambil pembacaan DHT22 dari node aktuator.

        Returns:
            {"ok": bool, "temp": float, "humidity": float}
            atau {"ok": False} jika offline/error.
        """
        try:
            r = requests.get(f"{self._base_url}/sensor",
                             timeout=self._timeout)
            if r.status_code == 200:
                data = r.json()
                self._online = True
                return data
        except Exception as e:
            print(f"[Actuator] get_sensor error: {e}")
            self._online = False
        return {"ok": False, "temp": 0.0, "humidity": 0.0}

    # ── Servo ─────────────────────────────────────────────────────────────────

    def click_servo(self, servo_id: int) -> bool:
        """
        Jalankan urutan klik servo dengan easing (sesuai kalibrasi tersimpan).

        Args:
            servo_id: 0 = Power, 1 = Temp Up, 2 = Temp Down

        Returns:
            True jika berhasil, False jika gagal.
        """
        try:
            r = requests.post(
                f"{self._base_url}/servo/click",
                params={"id": servo_id},
                timeout=self._timeout + 5  # klik butuh waktu lebih lama
            )
            self._online = True
            return r.status_code == 200
        except Exception as e:
            print(f"[Actuator] click_servo({servo_id}) error: {e}")
            self._online = False
            return False

    def move_servo(self, servo_id: int, angle: int) -> bool:
        """
        Gerakin servo ke sudut tertentu (untuk kalibrasi interaktif).

        Args:
            servo_id: 0-2
            angle: 0-180 derajat

        Returns:
            True jika berhasil.
        """
        try:
            r = requests.post(
                f"{self._base_url}/servo/move",
                params={"id": servo_id, "angle": angle},
                timeout=self._timeout
            )
            self._online = True
            return r.status_code == 200
        except Exception as e:
            print(f"[Actuator] move_servo({servo_id}, {angle}) error: {e}")
            self._online = False
            return False

    def save_calibration(self, servo_id: int,
                         stay_angle: int, click_angle: int) -> dict:
        """
        Simpan nilai kalibrasi servo ke LittleFS di node.

        Args:
            servo_id: 0-2
            stay_angle: Sudut posisi diam (0-180)
            click_angle: Sudut posisi klik (0-180); selisih dengan stay ≤ 120°

        Returns:
            Response JSON dari node, atau {"ok": False} jika gagal.
        """
        try:
            r = requests.post(
                f"{self._base_url}/servo/calibrate",
                params={
                    "id": servo_id,
                    "stay": stay_angle,
                    "click": click_angle
                },
                timeout=self._timeout
            )
            self._online = True
            return r.json()
        except Exception as e:
            print(f"[Actuator] save_calibration error: {e}")
            self._online = False
            return {"ok": False, "error": str(e)}

    def get_calibration(self) -> dict:
        """
        Ambil semua nilai kalibrasi servo dari node.

        Returns:
            Dict berisi konfigurasi per servo, atau {} jika offline.
        """
        try:
            r = requests.get(f"{self._base_url}/servo/config",
                             timeout=self._timeout)
            self._online = True
            return r.json()
        except Exception as e:
            print(f"[Actuator] get_calibration error: {e}")
            self._online = False
            return {}

    # ── Relay ─────────────────────────────────────────────────────────────────

    def set_relay(self, state: str) -> bool:
        """
        Kontrol relay lampu.

        Args:
            state: "ON" atau "OFF"

        Returns:
            True jika berhasil.
        """
        try:
            r = requests.post(
                f"{self._base_url}/relay",
                params={"state": state.upper()},
                timeout=self._timeout
            )
            self._online = True
            return r.status_code == 200
        except Exception as e:
            print(f"[Actuator] set_relay({state}) error: {e}")
            self._online = False
            return False
