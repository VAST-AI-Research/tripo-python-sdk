"""
Tripo 3D Generation API Client

A Python client for the Tripo 3D Generation API.
"""

import os
import threading
from .client import TripoClient
from .models import Animation, ModelStyle, PostStyle, RigType, RigSpec, Task, Balance, TaskStatus, TaskOutput
from .exceptions import TripoAPIError, TripoRequestError


def _detect_location_background():
    """Background thread to detect geographical location."""
    try:
        from .geo_utils import detect_china_mainland_sync, set_china_mainland_status

        # Only run detection if not disabled and not already detected
        if not os.getenv("TRIPO_DISABLE_GEO_DETECTION", "").lower() in ("1", "true", "yes"):
            result = detect_china_mainland_sync(timeout=1.0)  # Very short timeout for import
            if result is not None:
                set_china_mainland_status(result)
    except Exception:
        # Silently ignore any detection errors during import
        pass


# Start background detection (non-blocking)
_detection_thread = threading.Thread(target=_detect_location_background, daemon=True)
_detection_thread.start()

__version__ = "0.3.5"
__all__ = [
    "TripoClient",
    "Animation",
    "ModelStyle",
    "PostStyle",
    "RigType",
    "RigSpec",
    "Task",
    "Balance",
    "TaskStatus",
    "TaskOutput",
    "TripoAPIError",
    "TripoRequestError"
]
