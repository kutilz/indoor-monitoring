"""
Abstraksi sumber video — memungkinkan kode yang sama berjalan
baik dari file video lokal (mode akuisisi) maupun HTTP MJPEG stream
dari ESP32-CAM (mode real).
"""

import time
import cv2
import config


class StreamSource:
    """Base class untuk semua sumber video."""

    def read(self):
        """
        Baca satu frame dari sumber video.

        Returns:
            tuple: (success: bool, frame: np.ndarray | None)
        """
        raise NotImplementedError

    def release(self):
        """Lepaskan resource sumber video."""
        raise NotImplementedError

    def is_opened(self):
        """Cek apakah sumber video masih aktif."""
        raise NotImplementedError


class FileStreamSource(StreamSource):
    """
    Baca frame dari file video lokal (.mp4, .avi, dll).
    Mendukung looping otomatis saat video selesai (berguna untuk demo).
    """

    def __init__(self, path: str, loop: bool = True):
        self._path = path
        self._loop = loop
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise FileNotFoundError(
                f"Tidak dapat membuka file video: {path}\n"
                "Pastikan file ada di folder data/test_videos/"
            )
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._frame_delay = 1.0 / fps if fps > 0 else 1.0 / 20.0
        print(f"[FileStreamSource] Membuka: {path}")
        print(f"[FileStreamSource] {self._total_frames} frame @ {fps:.1f} fps")

    def read(self):
        time.sleep(self._frame_delay)
        success, frame = self._cap.read()

        if not success and self._loop:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            success, frame = self._cap.read()

        return success, frame

    def release(self):
        self._cap.release()

    def is_opened(self):
        return self._cap.isOpened()


class HttpStreamSource(StreamSource):
    """
    Baca frame dari HTTP MJPEG stream ESP32-CAM.
    Otomatis coba reconnect jika koneksi putus.
    """

    def __init__(self, url: str, retry_interval: float = 5.0,
                 max_retries: int = 0):
        """
        Args:
            url: URL MJPEG stream, contoh 'http://192.168.1.100/stream'
            retry_interval: Detik antar percobaan reconnect
            max_retries: 0 = coba selamanya
        """
        self._url = url
        self._retry_interval = retry_interval
        self._max_retries = max_retries
        self._cap = None
        self._connected = False
        self._connect()

    def _connect(self):
        attempt = 0
        while True:
            print(f"[HttpStreamSource] Menghubungkan ke: {self._url}")
            self._cap = cv2.VideoCapture(self._url)
            if self._cap.isOpened():
                self._connected = True
                print("[HttpStreamSource] Terhubung.")
                return
            attempt += 1
            if self._max_retries > 0 and attempt >= self._max_retries:
                raise ConnectionError(
                    f"Gagal terhubung ke stream setelah {attempt} percobaan.\n"
                    f"Periksa apakah ESP32-CAM aktif di: {self._url}"
                )
            print(
                f"[HttpStreamSource] Gagal. Coba lagi dalam "
                f"{self._retry_interval}s... (percobaan {attempt})"
            )
            time.sleep(self._retry_interval)

    def read(self):
        success, frame = self._cap.read()
        if not success:
            print("[HttpStreamSource] Frame gagal dibaca, reconnecting...")
            self._connected = False
            try:
                self._connect()
                success, frame = self._cap.read()
            except ConnectionError as e:
                print(f"[HttpStreamSource] ERROR: {e}")
                return False, None
        return success, frame

    def release(self):
        if self._cap:
            self._cap.release()

    def is_opened(self):
        return self._connected


def create_stream(mode: str, source_path: str = None) -> StreamSource:
    """
    Factory function — pilih implementasi StreamSource berdasarkan mode.

    Args:
        mode: "akuisisi" atau "real"
        source_path: Path file video (hanya untuk mode akuisisi).
                     Jika None, gunakan DEFAULT_TEST_VIDEO dari config.

    Returns:
        Instance StreamSource yang sesuai.
    """
    if mode == "akuisisi":
        path = source_path or config.DEFAULT_TEST_VIDEO
        return FileStreamSource(path=path, loop=config.VIDEO_LOOP)

    elif mode == "real":
        return HttpStreamSource(
            url=config.ESP32_STREAM_URL,
            retry_interval=5.0,
            max_retries=0
        )

    else:
        raise ValueError(
            f"Mode tidak dikenal: '{mode}'. Gunakan 'akuisisi' atau 'real'."
        )
