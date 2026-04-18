"""
Modul deteksi orang menggunakan YOLOv8.
Menginisialisasi model satu kali dan menyediakan interface
sederhana untuk inferensi per-frame.
"""

import os
import cv2
import numpy as np
import config


class Detection:
    """Hasil deteksi satu objek dalam sebuah frame."""

    __slots__ = ("x1", "y1", "x2", "y2", "confidence", "class_id",
                 "cx", "cy", "w", "h")

    def __init__(self, x1, y1, x2, y2, confidence, class_id):
        self.x1 = int(x1)
        self.y1 = int(y1)
        self.x2 = int(x2)
        self.y2 = int(y2)
        self.confidence = float(confidence)
        self.class_id = int(class_id)
        self.cx = (self.x1 + self.x2) // 2
        self.cy = (self.y1 + self.y2) // 2
        self.w = self.x2 - self.x1
        self.h = self.y2 - self.y1

    def __repr__(self):
        return (f"Detection(person, conf={self.confidence:.2f}, "
                f"center=({self.cx},{self.cy}))")


class YoloDetector:
    """
    Wrapper YOLOv8 untuk deteksi orang (class 'person').

    Penggunaan:
        detector = YoloDetector()
        detections = detector.detect(frame)
        annotated_frame = detector.draw(frame, detections)
    """

    def __init__(self,
                 model_path: str = None,
                 confidence: float = None,
                 device: str = None):
        """
        Args:
            model_path: Path ke file .pt. Default dari config.
            confidence: Threshold confidence. Default dari config.
            device: "cpu" atau "0" untuk GPU. Default dari config.
        """
        self._model_path = model_path or config.YOLO_MODEL_PATH
        self._confidence = confidence if confidence is not None \
            else config.YOLO_CONFIDENCE
        self._device = device or config.YOLO_DEVICE

        self._model = self._load_model()

    def _load_model(self):
        from ultralytics import YOLO

        if not os.path.exists(self._model_path):
            print(
                f"[YoloDetector] Model tidak ditemukan di: {self._model_path}\n"
                f"[YoloDetector] Mengunduh otomatis dari Ultralytics..."
            )

        print(f"[YoloDetector] Memuat model: {self._model_path} "
              f"(device={self._device})")
        model = YOLO(self._model_path)
        print("[YoloDetector] Model siap.")
        return model

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """
        Jalankan inferensi pada satu frame.

        Args:
            frame: BGR image sebagai numpy array (dari OpenCV)

        Returns:
            List Detection yang hanya berisi class 'person'.
        """
        results = self._model(
            frame,
            conf=self._confidence,
            classes=[config.YOLO_PERSON_CLASS_ID],
            device=self._device,
            verbose=False
        )

        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                detections.append(Detection(x1, y1, x2, y2, conf, cls))

        return detections

    def draw(self, frame: np.ndarray, detections: list[Detection],
             zone_split_y: int = None) -> np.ndarray:
        """
        Gambar bounding box, label, dan garis pembagi zona pada frame.

        Args:
            frame: Frame original (tidak dimodifikasi, dikopi)
            detections: Hasil dari detect()
            zone_split_y: Koordinat Y garis pembagi zona. Jika None,
                          tidak digambar.

        Returns:
            Frame baru dengan anotasi.
        """
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # Garis pembagi zona
        if zone_split_y is not None:
            cv2.line(annotated, (0, zone_split_y), (w, zone_split_y),
                     (0, 255, 255), 2)
            cv2.putText(annotated, "ZONA DEPAN", (10, zone_split_y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(annotated, "ZONA BELAKANG",
                        (10, zone_split_y + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        for det in detections:
            # Tentukan warna berdasarkan zona
            if zone_split_y is not None:
                color = (0, 200, 0) if det.cy < zone_split_y \
                    else (0, 100, 255)
            else:
                color = (0, 200, 0)

            cv2.rectangle(annotated, (det.x1, det.y1),
                          (det.x2, det.y2), color, 2)
            label = f"person {det.confidence:.2f}"
            cv2.putText(annotated, label, (det.x1, det.y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        # Overlay jumlah orang
        count_text = f"Terdeteksi: {len(detections)} orang"
        cv2.rectangle(annotated, (0, 0), (250, 32), (0, 0, 0), -1)
        cv2.putText(annotated, count_text, (6, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        return annotated
