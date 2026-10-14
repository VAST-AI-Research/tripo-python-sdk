"""Classification of the values accepted by apiv3 ``input`` fields."""

import os
import re
from pathlib import Path
from typing import Union

InputLike = Union[str, Path]

URL = "url"
FILE_TOKEN = "file_token"
TASK_ID = "task_id"
LOCAL_FILE = "local_file"

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def classify(value: InputLike) -> str:
    """Return one of ``url`` / ``file_token`` / ``task_id`` / ``local_file``.

    An existing local path always wins so that a file literally named like a UUID still uploads.
    Strings that are none of the above are passed through as ``file_token`` and left for the API
    to reject.
    """
    if isinstance(value, Path):
        return LOCAL_FILE
    text = str(value).strip()
    if text.startswith(("http://", "https://")):
        return URL
    if os.path.isfile(text):
        return LOCAL_FILE
    if _UUID_RE.match(text):
        return TASK_ID
    return FILE_TOKEN


def looks_like_path(value: str) -> bool:
    return (
        os.sep in value
        or "/" in value
        or bool(os.path.splitext(value)[1]) and not value.startswith("file_")
    )
