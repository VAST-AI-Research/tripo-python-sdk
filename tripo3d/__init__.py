"""
Tripo 3D Generation API Client

A Python client for the Tripo apiv3 API.
"""

import os
import threading
from ._version import __version__
from .client import TripoClient
from .models import (
    Animation,
    PostStyle,
    RigType,
    RigSpec,
    Task,
    Balance,
    TaskStatus,
    TaskOutput,
    BatchTaskResult,
    TaskUsageItem,
    PresignedUpload,
)
from .exceptions import (
    TripoError,
    TripoAPIError,
    TripoRequestError,
    TripoValidationError,
    TripoPollTimeoutError,
    TripoApiError,
    TripoNetworkError,
)


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

__all__ = [
    "TripoClient",
    "Animation",
    "PostStyle",
    "RigType",
    "RigSpec",
    "Task",
    "Balance",
    "TaskStatus",
    "TaskOutput",
    "BatchTaskResult",
    "TaskUsageItem",
    "PresignedUpload",
    "TripoError",
    "TripoAPIError",
    "TripoRequestError",
    "TripoValidationError",
    "TripoPollTimeoutError",
    "TripoApiError",
    "TripoNetworkError",
    "__version__",
]
