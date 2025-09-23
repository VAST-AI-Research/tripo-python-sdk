import os
import ssl
import aiohttp
from typing import Dict, Any, Optional
from ..exceptions import TripoAPIError, TripoRequestError
from .base_client import BaseClientImpl

class AioHttpClientImpl(BaseClientImpl):
    """Implementation using aiohttp library."""

    def __init__(self, api_key: str, base_url: str, verify_ssl: bool = True):
        super().__init__(api_key, base_url, verify_ssl)
        self._session: Optional[aiohttp.ClientSession] = None
        self._ssl_context = self._create_ssl_context(verify_ssl)

    def _create_ssl_context(self, verify_ssl: bool) -> Optional[ssl.SSLContext]:
        """Create SSL context based on verification settings."""
        if not verify_ssl:
            # Create an SSL context that doesn't verify certificates
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            return ssl_context
        return None  # Use default SSL context

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure that an aiohttp session exists."""
        if self._session is None or self._session.closed:
            # Create connector with SSL context
            connector = aiohttp.TCPConnector(ssl=self._ssl_context)
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.api_key}"},
                connector=connector
            )
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request to the API using aiohttp."""
        session = await self._ensure_session()
        url = self._url(path)

        try:
            async with session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                data=data,
                headers=headers
            ) as response:
                # Check if the response status is an error
                if response.status >= 400:
                    error_text = await response.text()
                    try:
                        error_data = await response.json()
                        if "code" in error_data and "message" in error_data:
                            raise TripoAPIError(
                                code=error_data["code"],
                                message=error_data["message"],
                                suggestion=error_data.get("suggestion")
                            )
                    except:
                        # If we can't parse the error as JSON, use the raw text
                        raise TripoRequestError(
                            status_code=response.status,
                            message=f"Request failed: {response.reason}. Response: {error_text}"
                        )

                # Try to parse the response as JSON
                try:
                    response_data = await response.json()
                except aiohttp.ContentTypeError as e:
                    # If the response is not JSON, raise an error with details
                    response_text = await response.text()
                    raise TripoRequestError(
                        status_code=response.status,
                        message=f"Failed to parse response as JSON. URL: {url}, Status: {response.status}, Content-Type: {response.headers.get('Content-Type')}, Response: {response_text[:200]}..."
                    )

                return response_data
        except aiohttp.ClientError as e:
            raise TripoRequestError(status_code=0, message=f"Request error for {url}: {str(e)}")

    async def upload_file(self, file_path: str) -> str:
        """Upload a file to the API using aiohttp."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        session = await self._ensure_session()
        url = self._url("/upload")

        try:
            with open(file_path, "rb") as f:
                form_data = aiohttp.FormData()
                form_data.add_field("file", f, filename=os.path.basename(file_path))

                async with session.post(url, data=form_data) as response:
                    response_data = await response.json()

                    if response.status >= 400:
                        if "code" in response_data and "message" in response_data:
                            raise TripoAPIError(
                                code=response_data["code"],
                                message=response_data["message"],
                                suggestion=response_data.get("suggestion")
                            )
                        else:
                            raise TripoRequestError(
                                status_code=response.status,
                                message=f"Upload failed: {response.reason}"
                            )

                    return response_data["data"]["image_token"]
        except aiohttp.ClientError as e:
            raise TripoRequestError(status_code=0, message=f"Upload error: {str(e)}")
        except IOError as e:
            raise TripoRequestError(status_code=0, message=f"File error: {str(e)}")

    async def download_file(self, url: str, output_path: str) -> None:
        """Download a file using aiohttp."""
        session = await self._ensure_session()

        try:
            async with session.get(url) as response:
                if response.status >= 400:
                    raise TripoRequestError(
                        status_code=response.status,
                        message=f"Failed to download: {response.reason}"
                    )

                with open(output_path, 'wb') as f:
                    chunk_size = 1024 * 1024  # 1MB chunks
                    async for chunk in response.content.iter_chunked(chunk_size):
                        if chunk:
                            f.write(chunk)
        except aiohttp.ClientError as e:
            raise TripoRequestError(
                status_code=0,
                message=f"Download error: {str(e)}"
            )
        except IOError as e:
            raise TripoRequestError(
                status_code=0,
                message=f"File error: {str(e)}"
            )