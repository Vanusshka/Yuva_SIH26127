"""
Vehicle Detector – wraps a pretrained YOLOv8 model.

Returns detected vehicles with class, bbox, and confidence.
Replace the model file in config.py to upgrade without touching this module.

If ultralytics is not installed the detector falls back to a stub that returns
an empty list so the server starts cleanly. Install ultralytics to enable
real vehicle detection.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

import numpy as np

try:
    from ultralytics import YOLO
    _ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None  # type: ignore
    _ULTRALYTICS_AVAILABLE = False

from app.config import VEHICLE_MODEL_NAME, VEHICLE_CONF_THRESH, VEHICLE_CLASS_IDS


@dataclass
class VehicleDetection:
    vehicle_class: str
    confidence: float
    bbox: List[int]          # [x1, y1, x2, y2]  absolute pixels


class VehicleDetector:
    """Singleton-style loader – model is loaded once and reused."""

    _instance: "VehicleDetector | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = None
        return cls._instance

    def _load(self):
        if not _ULTRALYTICS_AVAILABLE:
            return  # stub mode — detect() will return []
        if self._model is None:
            print(f"[VehicleDetector] Loading {VEHICLE_MODEL_NAME} ...")
            self._model = YOLO(VEHICLE_MODEL_NAME)
            print("[VehicleDetector] Model ready.")

    def detect(
        self,
        image: np.ndarray,
        conf_threshold: float = VEHICLE_CONF_THRESH,
    ) -> List[VehicleDetection]:
        """
        Run vehicle detection on a BGR numpy image.
        Returns empty list if ultralytics is not installed.
        """
        if not _ULTRALYTICS_AVAILABLE:
            return []
        self._load()

        results = self._model(
            image,
            classes=list(VEHICLE_CLASS_IDS.keys()),
            conf=conf_threshold,
            verbose=False,
        )[0]

        detections: List[VehicleDetection] = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            if cls_id not in VEHICLE_CLASS_IDS:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            detections.append(
                VehicleDetection(
                    vehicle_class=VEHICLE_CLASS_IDS[cls_id],
                    confidence=round(float(box.conf[0]), 4),
                    bbox=[x1, y1, x2, y2],
                )
            )

        return detections
