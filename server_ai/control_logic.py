"""
Logika kendali: deteksi orang → keputusan AC & lampu → perintah aktuator.

Perubahan dari versi lama:
  - Lampu disederhanakan jadi 1 relay tunggal (bukan zona depan/belakang)
  - AC dikontrol via klik servo power (bukan relay on/off)
  - Server melacak "ac_desired" karena tidak ada feedback fisik dari AC Daikin
  - Output: get_actuator_commands() menggantikan get_relay_commands()
"""

import threading
from dataclasses import dataclass, field
from yolo_detector import Detection
import config


@dataclass
class ControlState:
    """State kendali per frame — dikirim ke dashboard via SSE."""
    total_persons: int = 0
    zone_front: int    = 0   # Jumlah orang di zona atas frame (untuk visualisasi)
    zone_back: int     = 0   # Jumlah orang di zona bawah frame

    # Keputusan aktuator (desired state)
    ac_desired: bool   = False   # True = ingin AC menyala
    lamp_on: bool      = False   # True = ingin lampu menyala

    # Metadata untuk dashboard
    frame_width: int   = 0
    frame_height: int  = 0
    zone_split_y: int  = 0

    def to_dict(self) -> dict:
        return {
            "total_persons": self.total_persons,
            "zone_front":    self.zone_front,
            "zone_back":     self.zone_back,
            "ac_desired":    self.ac_desired,
            "lamp_on":       self.lamp_on,
            "frame_width":   self.frame_width,
            "frame_height":  self.frame_height,
            "zone_split_y":  self.zone_split_y,
        }


class ControlLogic:
    """
    Menghasilkan keputusan kendali berdasar jumlah orang terdeteksi.

    AC:
      - NYALA jika total_persons >= threshold_ac
      - MATI jika total_persons < threshold_ac
      - Dikontrol via klik servo power (toggle); server track state yang diinginkan

    Lampu:
      - NYALA jika total_persons >= threshold_lamp
      - MATI jika tidak ada orang
      - Dikontrol via relay tunggal

    State tracking AC:
      Server menyimpan "ac_presumed_on" (bool) karena tidak ada feedback fisik
      dari AC Daikin. Setiap kali state yang diinginkan berubah → klik servo power.
    """

    def __init__(self,
                 zone_split_ratio: float = None,
                 threshold_ac: int = None,
                 threshold_lamp: int = None):
        self._zone_split_ratio = (
            zone_split_ratio if zone_split_ratio is not None
            else config.ZONE_SPLIT_RATIO
        )
        self._threshold_ac   = (
            threshold_ac if threshold_ac is not None
            else config.PERSON_THRESHOLD_AC
        )
        self._threshold_lamp = (
            threshold_lamp if threshold_lamp is not None
            else config.PERSON_THRESHOLD_LAMP
        )

        self._prev_state    = ControlState()
        self._ac_presumed   = False   # Apa yang server anggap sebagai state AC fisik
        self._lock          = threading.Lock()

    # ── Parameter update (dari dashboard settings) ────────────────────────────

    def update_params(self,
                      zone_split_ratio: float = None,
                      threshold_ac: int = None,
                      threshold_lamp: int = None):
        """Update parameter runtime tanpa restart (dipanggil dari API settings)."""
        with self._lock:
            if zone_split_ratio is not None:
                self._zone_split_ratio = zone_split_ratio
            if threshold_ac is not None:
                self._threshold_ac = threshold_ac
            if threshold_lamp is not None:
                self._threshold_lamp = threshold_lamp

    # ── Proses frame ─────────────────────────────────────────────────────────

    def process(self, detections: list,
                frame_width: int, frame_height: int) -> ControlState:
        """
        Hitung state kendali dari hasil deteksi YOLO.

        Args:
            detections: List Detection dari YoloDetector.detect()
            frame_width, frame_height: Dimensi frame dalam piksel

        Returns:
            ControlState dengan keputusan terbaru.
        """
        with self._lock:
            split_ratio = self._zone_split_ratio
            thr_ac      = self._threshold_ac
            thr_lamp    = self._threshold_lamp

        split_y    = int(frame_height * split_ratio)
        zone_front = [d for d in detections if d.cy < split_y]
        zone_back  = [d for d in detections if d.cy >= split_y]
        total      = len(detections)

        state = ControlState(
            total_persons = total,
            zone_front    = len(zone_front),
            zone_back     = len(zone_back),
            ac_desired    = (total >= thr_ac),
            lamp_on       = (total >= thr_lamp),
            frame_width   = frame_width,
            frame_height  = frame_height,
            zone_split_y  = split_y,
        )
        return state

    # ── Perintah aktuator ─────────────────────────────────────────────────────

    def get_actuator_commands(self,
                              new_state: ControlState,
                              old_state: ControlState = None) -> dict:
        """
        Bandingkan state baru vs lama, hasilkan daftar perintah yang perlu dieksekusi.

        AC menggunakan pola toggle (klik power sekali untuk nyala/mati).
        Server melacak "ac_presumed" agar tidak double-klik.

        Lampu pakai relay langsung (no toggle needed).

        Returns:
            {
                "servo_clicks": [int, ...],   # list servo ID yang harus diklik
                "relay": "ON" | "OFF" | None  # perintah relay lampu, atau None jika tidak berubah
            }
        """
        if old_state is None:
            old_state = self._prev_state

        commands = {
            "servo_clicks": [],
            "relay": None,
            "log_entries": []
        }

        # ── AC: klik power jika desired state berubah ─────────────────────────
        if new_state.ac_desired != old_state.ac_desired:
            # Toggle: apapun state fisik AC, kita klik sekali
            # (Kita track ac_presumed untuk mencegah double klik jika logic error)
            if new_state.ac_desired != self._ac_presumed:
                commands["servo_clicks"].append(config.SERVO_POWER)
                self._ac_presumed = new_state.ac_desired
                commands["log_entries"].append({
                    "actuator": "AC Power",
                    "action":   "KLIK",
                    "reason":   "ON" if new_state.ac_desired else "OFF",
                })

        # ── Lampu: relay langsung, hanya kirim jika berubah ──────────────────
        if new_state.lamp_on != old_state.lamp_on:
            commands["relay"] = "ON" if new_state.lamp_on else "OFF"
            commands["log_entries"].append({
                "actuator": "Lampu",
                "action":   "ON" if new_state.lamp_on else "OFF",
                "reason":   f"{new_state.total_persons} orang",
            })

        self._prev_state = new_state
        return commands

    def force_ac_state(self, desired_on: bool):
        """
        Override manual AC dari dashboard.
        Klik servo power dan update tracking.
        Dipanggil oleh endpoint /api/ac/power.
        """
        self._ac_presumed = desired_on
        self._prev_state.ac_desired = desired_on
