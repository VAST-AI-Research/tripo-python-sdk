import os
import json
import asyncio
import ssl
import mimetypes
import uuid
from urllib.parse import urlparse, urlencode
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from ..exceptions import TripoAPIError, TripoRequestError
from .base_client import BaseClientImpl

# Legacy implementation using raw sockets
class MultipartFormData:
    """Helper class for building multipart/form-data requests."""

    def __init__(self):
        self.boundary = f"boundary-{uuid.uuid4()}"
        self.parts: List[Tuple[Dict[str, str], bytes]] = []

    def add_field(self, name: str, value: Any, filename: Optional[str] = None):
        """Add a field to the form data."""
        headers = {
            'Content-Disposition': f'form-data; name="{name}"'
            + (f'; filename="{filename}"' if filename else '')
        }

        if filename:
            content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            headers['Content-Type'] = content_type

        if isinstance(value, bytes):
            data = value
        else:
            data = str(value).encode('utf-8')

        self.parts.append((headers, data))

    def build(self) -> Tuple[bytes, str]:
        """Build the multipart form data."""
        lines = []
        for headers, data in self.parts:
            lines.append(f'--{self.boundary}'.encode('utf-8'))
            for key, value in headers.items():
                lines.append(f'{key}: {value}'.encode('utf-8'))
            lines.append(b'')
            lines.append(data)

        lines.append(f'--{self.boundary}--'.encode('utf-8'))
        lines.append(b'')

        body = b'\r\n'.join(lines)
        content_type = f'multipart/form-data; boundary={self.boundary}'
        return body, content_type


@dataclass
class HttpResponse:
    """HTTP response container."""
    status: int
    headers: Dict[str, str]
    body: bytes


class LegacyClientImpl(BaseClientImpl):
    """Implementation using raw sockets."""

    def __init__(self, api_key: str, base_url: str, verify_ssl: bool = True):
        super().__init__(api_key, base_url, verify_ssl)
        self._ssl_context = self._create_ssl_context(verify_ssl)
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._host = urlparse(base_url).netloc

    def _create_ssl_context(self, verify_ssl: bool) -> ssl.SSLContext:
        """Create SSL context based on verification settings."""
        if not verify_ssl:
            # Create an SSL context that doesn't verify certificates
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            return ssl_context
        return ssl.create_default_context()  # Use default SSL context

    async def _connect(self) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Establish connection to the API server."""
        if not self._reader or not self._writer:
            self._reader, self._writer = await asyncio.open_connection(
                self._host, 443, ssl=self._ssl_context
            )
        return self._reader, self._writer

    async def close(self) -> None:
        """Close the connection."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    async def _read_response(self, reader: asyncio.StreamReader) -> HttpResponse:
        """Read and parse HTTP response."""
        # Read status line
        status_line = await reader.readline()
        version, status, *reason = status_line.decode().split()
        status = int(status)

        # Read headers
        headers = {}
        while True:
            line = await reader.readline()
            if line == b'\r\n':
                break
            name, value = line.decode().strip().split(':', 1)
            headers[name.lower()] = value.strip()

        # Read body
        body = b''
        if 'content-length' in headers:
            content_length = int(headers['content-length'])
            body = await reader.readexactly(content_length)
        elif headers.get('transfer-encoding') == 'chunked':
            while True:
                size_line = await reader.readline()
                chunk_size = int(size_line.decode().strip(), 16)
                if chunk_size == 0:
                    await reader.readline()  # Read final CRLF
                    break
                chunk = await reader.readexactly(chunk_size)
                body += chunk
                await reader.readline()  # Read CRLF after chunk

        return HttpResponse(status, headers, body)

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request to the API using raw sockets."""
        url = self._url(path)
        parsed_url = urlparse(url)

        # Prepare headers
        headers = headers or {}
        headers.update({
            'Host': parsed_url.netloc,
            'Authorization': f'Bearer {self.api_key}',
            'Connection': 'keep-alive'
        })

        # Add query parameters
        query = urlencode(params or {})
        path = f"{parsed_url.path}{'?' + query if query else ''}"

        # Prepare request body
        if json_data is not None:
            data = json.dumps(json_data).encode('utf-8')
            headers['Content-Type'] = 'application/json'

        if data:
            headers['Content-Length'] = str(len(data))

        # Build request
        request_lines = [
            f"{method} {path} HTTP/1.1",
            *[f"{k}: {v}" for k, v in headers.items()],
            "",
            ""
        ]
        request = "\r\n".join(request_lines).encode('utf-8')

        # Send request
        reader, writer = await self._connect()
        writer.write(request)
        if data:
            writer.write(data)
        await writer.drain()

        # Read response
        response = await self._read_response(reader)

        # Parse response
        try:
            response_data = json.loads(response.body)

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
                        message=f"Request failed: {response_data}"
                    )

            return response_data

        except json.JSONDecodeError:
            raise TripoRequestError(
                status_code=response.status,
                message=f"Failed to parse response as JSON. Response: {response.body.decode('utf-8')[:200]}..."
            )

    async def upload_file(self, file_path: str) -> str:
        """Upload a file to the API using raw sockets."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        form = MultipartFormData()
        with open(file_path, 'rb') as f:
            form.add_field('file', f.read(), os.path.basename(file_path))

        body, content_type = form.build()
        headers = {'Content-Type': content_type}

        response = await self._request('POST', '/upload', data=body, headers=headers)
        return response['data']['image_token']

    async def download_file(self, url: str, output_path: str) -> None:
        """Download a file using raw sockets."""
        parsed_url = urlparse(url)

        headers = {
            'Host': parsed_url.netloc,
            'Authorization': f'Bearer {self.api_key}',
            'Connection': 'keep-alive'
        }

        path = parsed_url.path
        if parsed_url.query:
            path = f"{path}?{parsed_url.query}"

        request_lines = [
            f"GET {path} HTTP/1.1",
            *[f"{k}: {v}" for k, v in headers.items()],
            "",
            ""
        ]
        request = "\r\n".join(request_lines).encode('utf-8')

        reader, writer = await asyncio.open_connection(
            parsed_url.netloc, 443, ssl=self._ssl_context
        )

        try:
            writer.write(request)
            await writer.drain()

            response = await self._read_response(reader)

            if response.status >= 400:
                raise TripoRequestError(
                    status_code=response.status,
                    message=f"Failed to download: HTTP {response.status}"
                )

            with open(output_path, 'wb') as f:
                f.write(response.body)

        finally:
            writer.close()
            await writer.wait_closed()
