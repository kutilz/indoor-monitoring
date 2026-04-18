"""
Logika kendali zoning dan counting.
Menerima hasil deteksi dari YoloDetector, menghitung jumlah orang
per zona, lalu mengeluarkan keputusan on/off untuk setiap aktuator.
"""

from dataclasses import dataclass, field
from yolo_detector import Detection
import config


@dataclass
class ControlState:
    """
    Representasi state kendali sistem yang dihasilkan setiap frame.
    State ini dikirim ke MQTT dan ke dashboard.
    """
    total_persons: int = 0
    zone_front: int = 0       # Jumlah orang di zona depan
    zone_back: int = 0        # Jumlah orang di zona belakang

    ac_on: bool = False
    light_front_on: bool = False
    light_back_on: bool = False

    # Metadata untuk dashboard & logging
    frame_width: int = 0
    frame_height: int = 0
    zone_split_y: int = 0     # Koordinat piksel Y garis pembagi

    def to_dict(self) -> dict:
        return {
            "total_persons": self.total_persons,
            "zone_front": self.zone_front,
            "zone_back": self.zone_back,
            "ac_on": self.ac_on,
            "light_front_on": self.light_front_on,
            "light_back_on": self.light_back_on,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "zone_split_y": self.zone_split_y,
        }


class ControlLogic:
    """
    Menerapkan logika kendali berdasarkan deteksi orang dan konfigurasi zona.

    Zona ditentukan secara vertikal berdasarkan posisi center-Y bounding box:
    - Zona DEPAN  : cy < zone_split_y  (bagian atas frame)
    - Zona BELAKANG: cy >= zone_split_y (bagian bawah frame)

    Aturan kendali:
    - AC         : ON jika total_persons >= PERSON_THRESHOLD_AC
    - Lampu Depan : ON jika ada >= 1 orang di zona depan
    - Lampu Belakang: ON jika ada >= 1 orang di zona belakang
    """

    def __init__(self,
                 zone_split_ratio: float = None,
                 person_threshold_ac: int = None):
        """
        Args:
            zone_split_ratio: 0.0-1.0, rasio tinggi frame untuk pembagi zona.
            person_threshold_ac: Minimal orang agar AC menyala.
        """
        self._zone_split_ratio = zone_split_ratio \
            if zone_split_ratio is not None \
            else config.ZONE_SPLIT_RATIO
        self._threshold_ac = person_threshold_ac \
            if person_threshold_ac is not None \
            else config.PERSON_THRESHOLD_AC

        self._prev_state = ControlState()

    def process(self, detections: list[Detection],
                frame_width: int, frame_height: int) -> ControlState:
        """
        Hitung state kendali dari hasil deteksi.

        Args:
            detections: List Detection dari YoloDetector.detect()
            frame_width: Lebar frame dalam piksel
            frame_height: Tinggi frame dalam piksel

        Returns:
            ControlState dengan keputusan terbaru.
        """
        split_y = int(frame_height * self._zone_split_ratio)

        zone_front = [d for d in detections if d.cy < split_y]
        zone_back  = [d for d in detections if d.cy >= split_y]

        total = len(detections)
        n_front = len(zone_front)
        n_back  = len(zone_back)

        state = ControlState(
            total_persons=total,
            zone_front=n_front,
            zone_back=n_back,
            ac_on=(total >= self._threshold_ac),
            light_front_on=(n_front >= 1),
            light_back_on=(n_back >= 1),
            frame_width=frame_width,
            frame_height=frame_height,
            zone_split_y=split_y,
        )
        return state

    def get_relay_commands(self,
                           new_state: ControlState,
                           old_state: ControlState = None
                           ) -> list[dict]:
        """
        Bandingkan state baru dengan state lama.
        Return hanya perintah relay yang berubah (menghindari spam MQTT).

        Returns:
            List dict: [{"relay": int, "state": "ON"|"OFF"}, ...]
        """
        if old_state is None:
            old_state = self._prev_state

        commands = []

        checks = [
            (config.RELAY_AC,          old_state.ac_on,
             new_state.ac_on,          "AC"),
            (config.RELAY_LIGHT_FRONT, old_state.light_front_on,
             new_state.light_front_on, "Lampu Depan"),
            (config.RELAY_LIGHT_BACK,  old_state.light_back_on,
             new_state.light_back_on,  "Lampu Belakang"),
        ]

        for relay_num, was_on, is_on, name in checks:
            if was_on != is_on:
                state_str = "ON" if is_on else "OFF"
                commands.append({
                    "relay": relay_num,
                    "state": state_str,
                    "name": name,
                })

        self._prev_state = new_state
        return commands
