"""Detecção de rosto para focus point de crop (alternativa ao center-crop padrão)."""
import os
from typing import Optional, Tuple

import numpy as np

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "models", "blaze_face_short_range.tflite")

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    mp = None
    mp_python = None
    mp_vision = None

_detector = None
_detector_failed = False


def _get_detector():
    """Lazy singleton — cada processo worker cria o seu na primeira chamada."""
    global _detector, _detector_failed
    if _detector is not None or _detector_failed:
        return _detector
    if not MEDIAPIPE_AVAILABLE or not os.path.isfile(_MODEL_PATH):
        _detector_failed = True
        return None
    try:
        base_options = mp_python.BaseOptions(model_asset_path=_MODEL_PATH)
        options = mp_vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=0.5,
        )
        _detector = mp_vision.FaceDetector.create_from_options(options)
    except Exception as e:
        print(f"[FaceDetector] Falha ao inicializar mediapipe: {e}")
        _detector_failed = True
        _detector = None
    return _detector


def detect_focus_point(frame: np.ndarray) -> Optional[Tuple[float, float]]:
    """Recebe um frame RGB (H, W, 3) uint8 e retorna o centro (x, y) em pixels
    do maior rosto detectado, ou None se nenhum rosto foi encontrado / detector
    indisponível."""
    detector = _get_detector()
    if detector is None:
        return None

    try:
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame))
        result = detector.detect(mp_image)
    except Exception as e:
        print(f"[FaceDetector] Falha na detecção: {e}")
        return None

    if not result.detections:
        return None

    # Maior rosto detectado (mais provável de ser o sujeito principal)
    best = max(result.detections, key=lambda d: d.bounding_box.width * d.bounding_box.height)
    bbox = best.bounding_box
    return (bbox.origin_x + bbox.width / 2, bbox.origin_y + bbox.height / 2)
