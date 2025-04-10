"""
Unit tests for exceptions.
"""

import pytest

from tripo3d.exceptions import TripoAPIError, TripoRequestError


class TestTripoAPIError:
    """Test suite for the TripoAPIError class."""
    
    def test_init_with_all_fields(self):
        """Test initializing the exception with all fields."""
        error = TripoAPIError(code=2000, message="Error message", suggestion="Suggestion")
        
        assert error.code == 2000
        assert error.message == "Error message"
        assert error.suggestion == "Suggestion"
        assert str(error) == "[2000] Error message Suggestion: Suggestion"
    
    def test_init_without_suggestion(self):
        """Test initializing the exception without a suggestion."""
        error = TripoAPIError(code=2000, message="Error message")
        
        assert error.code == 2000
        assert error.message == "Error message"
        assert error.suggestion is None
        assert str(error) == "[2000] Error message"


class TestTripoRequestError:
    """Test suite for the TripoRequestError class."""
    
    def test_init(self):
        """Test initializing the exception."""
        error = TripoRequestError(status_code=404, message="Not found")
        
        assert error.status_code == 404
        assert error.message == "Not found"
        assert str(error) == "HTTP 404: Not found" 