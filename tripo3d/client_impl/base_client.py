from typing import Dict, Any, Optional

# Base client implementation
class BaseClientImpl:
    """Base implementation for Tripo API client."""

    def __init__(self, api_key: str, base_url: str, verify_ssl: bool = True):
        self.api_key = api_key
        self.base_url = base_url
        self.verify_ssl = verify_ssl

    def _url(self, path: str) -> str:
        """Construct a full URL from a path."""
        path = path.lstrip('/')
        return f"{self.base_url}/{path}"

    async def close(self) -> None:
        """Close any open connections."""
        pass

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request to the API."""
        raise NotImplementedError("Subclasses must implement _request")

    async def upload_file(self, file_path: str) -> str:
        """Upload a file to the API."""
        raise NotImplementedError("Subclasses must implement upload_file")

    async def download_file(self, url: str, output_path: str) -> None:
        """Download a file from a URL and save it to a local path."""
        raise NotImplementedError("Subclasses must implement download_file")
