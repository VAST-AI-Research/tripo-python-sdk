"""
Exceptions for the Tripo API client.
"""

class TripoAPIError(Exception):
    """Base exception for Tripo API errors."""

    def __init__(self, code, message, suggestion=None):
        self.code = code
        self.message = message
        self.suggestion = suggestion
        super().__init__(f"[{code}] {message}" + (f" Suggestion: {suggestion}" if suggestion else ""))


class TripoRequestError(Exception):
    """Exception for HTTP request errors."""

    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}") 
