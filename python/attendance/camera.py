"""Bounded JPEG validation and local QR decoding; images never leave this server."""
import io

import cv2
import numpy as np
from PIL import Image

MAX_CAMERA_BYTES = 262144
MAX_CAMERA_WIDTH = 800
MAX_CAMERA_HEIGHT = 600

# One scanner already serializes capture; avoid native thread oversubscription.
cv2.setNumThreads(1)


def decode_frame(frame):
    """Return (credential, pattern_seen), accepting only a bounded JPEG image."""
    try:
        with Image.open(io.BytesIO(frame)) as image:
            if (image.format != "JPEG" or not 32 <= image.width <= MAX_CAMERA_WIDTH
                    or not 32 <= image.height <= MAX_CAMERA_HEIGHT):
                raise ValueError("Unsupported camera dimensions or format")
            image.verify()
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("Invalid camera image") from error
    image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("Invalid JPEG data")
    detector = cv2.QRCodeDetector()
    try:
        payload, points, _ = detector.detectAndDecode(image)
        # Some mountings produce a mirrored QR. Retry only when a pattern exists.
        if not payload and points is not None:
            payload, _, _ = detector.detectAndDecode(cv2.flip(image, 1))
    except UnicodeDecodeError:
        return "unsupported-binary-card", True
    return payload, points is not None
