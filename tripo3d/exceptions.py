"""
Exceptions for the Tripo API client.
"""

import asyncio
from typing import Optional


class TripoError(Exception):
    """Base class for every exception raised by the SDK."""


class TripoAPIError(TripoError):
    """The API answered with a non-zero business ``code``."""

    def __init__(self, code, message, suggestion=None, request_id: Optional[str] = None):
        self.code = code
        self.message = message
        self.suggestion = suggestion
        self.request_id = request_id
        text = f"[{code}] {message}" + (f" Suggestion: {suggestion}" if suggestion else "")
        if request_id:
            text += f" (request_id={request_id})"
        super().__init__(text)


class TripoRequestError(TripoError):
    """HTTP / transport failure without a business error body."""

    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class TripoValidationError(TripoError, ValueError):
    """Client-side argument validation failure."""


class TripoPollTimeoutError(TripoError, asyncio.TimeoutError):
    """``wait_for_task`` exceeded its ``timeout``."""

    def __init__(self, task_id: str, timeout_seconds: float):
        self.task_id = task_id
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Task {task_id} did not complete within {timeout_seconds} seconds")


TripoApiError = TripoAPIError
TripoNetworkError = TripoRequestError
