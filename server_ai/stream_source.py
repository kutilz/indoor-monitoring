"""
Abstraksi sumber video — HTTP MJPEG stream dari ESP32-CAM.
Auto-reconnect dengan exponential backoff jika stream terputus.
"""

import time
import cv2
import config


class HttpStreamSource:
    """
    Membaca frame dari MJPEG stream ESP32-CAM via HTTP.
    Auto-reconnect dengan exponential backoff (1s → 2s → 4s → max 30s).
    """

    def __init__(self, url: str = None):
        self._url      = url or config.ESP32_STREAM_URL
        self._cap      = None
        self._backoff  = 1.0   # Interval reconnect awal (detik)
        self._max_back = 30.0  # Interval reconnect maksimum (detik)
        self._connect()

    def _connect(self):
        """Buka koneksi ke MJPEG stream."""
        print(f"[Camera] Menghubungkan ke: {self._url}")
        if self._cap:
            self._cap.release()
        self._cap = cv2.VideoCapture(self._url)
        if self._cap.isOpened():
            print("[Camera] Stream terhubung.")
            self._backoff = 1.0  # Reset backoff setelah berhasil
        else:
            print(f"[Camera] Gagal terhubung. Retry dalam {self._backoff:.0f}s...")

    def read(self):
        """
        Baca satu frame dari stream.

        Returns:
            (success: bool, frame: np.ndarray | None)
        """
        if self._cap is None or not self._cap.isOpened():
            time.sleep(self._backoff)
            self._backoff = min(self._backoff * 2, self._max_back)
            self._connect()
            return False, None

        success, frame = self._cap.read()

        if not success:
            print(f"[Camera] Frame gagal dibaca. Retry dalam {self._backoff:.0f}s...")
            time.sleep(self._backoff)
            self._backoff = min(self._backoff * 2, self._max_back)
            self._connect()
            return False, None

        return True, frame

    @property
    def is_connected(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def release(self):
        if self._cap:
            self._cap.release()
            print("[Camera] Stream dilepas.")
