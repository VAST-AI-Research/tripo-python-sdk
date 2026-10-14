"""HTTP transport for apiv3: aiohttp when installed, otherwise a zero-dependency asyncio client."""

import asyncio
import importlib.util
import json
import mimetypes
import os
import ssl
import uuid
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode, urlparse

from ._version import __version__
from .exceptions import TripoAPIError, TripoRequestError

USER_AGENT = f"tripo3d-python/{__version__}"

# Only idempotent reads are retried; task creation is never replayed (it would bill twice).
_RETRY_STATUSES = frozenset({429, 502, 503, 504})
_GET_ATTEMPTS = 3
_RETRY_AFTER_CAP_SECONDS = 10.0

API_TIMEOUT_SECONDS = 120
CONNECT_TIMEOUT_SECONDS = 30
DOWNLOAD_READ_TIMEOUT_SECONDS = 300


def create_http_backend(api_key: str, base_url: str, verify_ssl: bool = True) -> "HttpBackend":
    if importlib.util.find_spec("aiohttp") is not None:
        return AioHttpBackend(api_key, base_url, verify_ssl=verify_ssl)
    return FallbackBackend(api_key, base_url, verify_ssl=verify_ssl)


def _retry_delay(attempt: int, retry_after: Optional[str]) -> float:
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), _RETRY_AFTER_CAP_SECONDS)
        except ValueError:
            pass
    return min(0.5 * (2 ** attempt), _RETRY_AFTER_CAP_SECONDS)


def _api_error_from_body(status: int, text: str, reason: str) -> Exception:
    try:
        body = json.loads(text) if text else {}
    except json.JSONDecodeError:
        body = {}
    if isinstance(body, dict) and body.get("code") not in (None, 0):
        return TripoAPIError(
            code=body.get("code"),
            message=body.get("message") or reason,
            suggestion=body.get("suggestion"),
            request_id=body.get("request_id"),
        )
    return TripoRequestError(status_code=status, message=f"{reason}. Response: {text[:500]}")


class HttpBackend:
    """Common envelope handling; subclasses implement the wire calls."""

    def __init__(self, api_key: str, base_url: str, verify_ssl: bool = True):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _api_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "X-Tripo-Trace-ID": str(uuid.uuid4()),
        }
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def parse_envelope(payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        code = payload.get("code")
        if (code is not None and code != 0) or payload.get("status") == "error":
            raise TripoAPIError(
                code=code if code is not None else -1,
                message=payload.get("message") or "API error",
                suggestion=payload.get("suggestion"),
                request_id=payload.get("request_id"),
            )
        return payload.get("data") if "data" in payload else payload

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        attempts = _GET_ATTEMPTS if method.upper() == "GET" else 1
        for attempt in range(attempts):
            try:
                status, text, retry_after = await self._send(method, self._url(path), params, json_data)
            except TripoRequestError:
                if attempt + 1 >= attempts:
                    raise
                await asyncio.sleep(_retry_delay(attempt, None))
                continue
            if status in _RETRY_STATUSES and attempt + 1 < attempts:
                await asyncio.sleep(_retry_delay(attempt, retry_after))
                continue
            if status >= 400:
                raise _api_error_from_body(status, text, f"HTTP {status}")
            if not text:
                return {}
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise TripoRequestError(status, f"Failed to parse JSON: {exc}. Body: {text[:200]}") from exc
            return self.parse_envelope(payload)
        raise TripoRequestError(0, "unreachable")

    async def close(self) -> None:
        return None

    async def _send(
        self, method: str, url: str, params: Optional[Dict[str, Any]], json_data: Optional[Dict[str, Any]]
    ) -> Tuple[int, str, Optional[str]]:
        raise NotImplementedError

    async def upload_multipart(self, path: str, file_path: str, field_name: str = "file") -> Any:
        raise NotImplementedError

    async def put_file(self, url: str, file_path: str, content_type: str) -> None:
        raise NotImplementedError

    async def download_file(self, url: str, output_path: str) -> None:
        raise NotImplementedError


class AioHttpBackend(HttpBackend):
    """One short-lived session per operation.

    Callers routinely drop a client without ``close()`` (ComfyUI nodes create one per run), and a
    long-lived aiohttp session left behind leaks its connections. Polling is seconds apart, so
    connection reuse would buy little.
    """

    def _ssl(self):
        if self.verify_ssl:
            return None
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _session(self):
        import aiohttp

        # No default Authorization header: sessions also download signed CDN URLs and PUT to
        # presigned storage URLs, neither of which may receive the API key.
        return aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self._ssl()),
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=CONNECT_TIMEOUT_SECONDS),
        )

    async def _send(self, method, url, params, json_data):
        import aiohttp

        headers = self._api_headers({"Content-Type": "application/json"} if json_data is not None else None)
        clean_params = {k: v for k, v in (params or {}).items() if v is not None} or None
        try:
            async with self._session() as session, session.request(
                method,
                url,
                params=clean_params,
                json=json_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                text = await response.text()
                return response.status, text, response.headers.get("Retry-After")
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise TripoRequestError(0, f"Request error for {url}: {exc}") from exc

    async def upload_multipart(self, path, file_path, field_name="file"):
        import aiohttp

        url = self._url(path)
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        try:
            with open(file_path, "rb") as handle:
                form = aiohttp.FormData()
                form.add_field(field_name, handle, filename=filename, content_type=content_type)
                async with self._session() as session, session.post(
                    url, data=form, headers=self._api_headers()
                ) as response:
                    text = await response.text()
                    if response.status >= 400:
                        raise _api_error_from_body(response.status, text, "Upload failed")
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise TripoRequestError(0, f"Upload error: {exc}") from exc
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            raise TripoRequestError(0, f"Failed to parse upload response: {exc}") from exc
        return self.parse_envelope(payload)

    async def put_file(self, url, file_path, content_type):
        import aiohttp

        size = os.path.getsize(file_path)
        try:
            with open(file_path, "rb") as handle:
                async with self._session() as session, session.put(
                    url,
                    data=handle,
                    headers={"Content-Type": content_type, "Content-Length": str(size)},
                ) as response:
                    if response.status >= 400:
                        body = await response.text()
                        raise TripoRequestError(response.status, f"Presigned PUT failed: {body[:300]}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise TripoRequestError(0, f"Presigned PUT error: {exc}") from exc

    async def download_file(self, url, output_path):
        import aiohttp

        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        try:
            async with self._session() as session, session.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(
                    total=None, sock_connect=CONNECT_TIMEOUT_SECONDS, sock_read=DOWNLOAD_READ_TIMEOUT_SECONDS
                ),
            ) as response:
                if response.status >= 400:
                    raise TripoRequestError(response.status, f"Failed to download file: {response.reason}")
                with open(output_path, "wb") as handle:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        handle.write(chunk)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise TripoRequestError(0, f"Download error: {exc}") from exc


class FallbackBackend(HttpBackend):
    """HTTP/1.1 over asyncio streams for environments without aiohttp."""

    async def _send(self, method, url, params, json_data):
        if params:
            query = urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url = f"{url}{'&' if '?' in url else '?'}{query}"
        headers = self._api_headers()
        body = None
        if json_data is not None:
            body = json.dumps(json_data).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))
        status, resp_headers, data = await self._raw(method, url, headers, body)
        return status, data.decode("utf-8", errors="replace"), resp_headers.get("retry-after")

    async def upload_multipart(self, path, file_path, field_name="file"):
        boundary = f"----TripoBoundary{uuid.uuid4().hex}"
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(file_path, "rb") as handle:
            file_bytes = handle.read()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
        headers = self._api_headers({
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        })
        status, _, data = await self._raw("POST", self._url(path), headers, body)
        text = data.decode("utf-8", errors="replace")
        if status >= 400:
            raise _api_error_from_body(status, text, "Upload failed")
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            raise TripoRequestError(status, f"Failed to parse upload response: {exc}") from exc
        return self.parse_envelope(payload)

    async def put_file(self, url, file_path, content_type):
        with open(file_path, "rb") as handle:
            data = handle.read()
        headers = {"Content-Type": content_type, "Content-Length": str(len(data)), "User-Agent": USER_AGENT}
        status, _, body = await self._raw("PUT", url, headers, data)
        if status >= 400:
            raise TripoRequestError(status, f"Presigned PUT failed: {body[:300]!r}")

    async def download_file(self, url, output_path):
        status, _, body = await self._raw("GET", url, {"User-Agent": USER_AGENT}, None)
        if status >= 400:
            raise TripoRequestError(status, "Failed to download file")
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(output_path, "wb") as handle:
            handle.write(body)

    async def _raw(self, method: str, url: str, headers: Dict[str, str], body: Optional[bytes]):
        parsed = urlparse(url)
        if not parsed.hostname:
            raise TripoRequestError(0, f"Invalid URL: {url}")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        lines = [f"{method.upper()} {target} HTTP/1.1", f"Host: {parsed.hostname}"]
        lines += [f"{k}: {v}" for k, v in headers.items()]
        lines += ["Connection: close", "", ""]
        payload = "\r\n".join(lines).encode("utf-8") + (body or b"")

        ssl_ctx = None
        if parsed.scheme == "https":
            ssl_ctx = ssl.create_default_context()
            if not self.verify_ssl:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(parsed.hostname, port, ssl=ssl_ctx), CONNECT_TIMEOUT_SECONDS
            )
            writer.write(payload)
            await writer.drain()
            raw = await asyncio.wait_for(reader.read(), DOWNLOAD_READ_TIMEOUT_SECONDS)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        except (OSError, asyncio.TimeoutError) as exc:
            raise TripoRequestError(0, f"Connection error: {exc}") from exc
        return self._split(raw)

    @staticmethod
    def _split(raw: bytes):
        end = raw.find(b"\r\n\r\n")
        if end < 0:
            raise TripoRequestError(0, "Malformed HTTP response")
        head = raw[:end].decode("iso-8859-1", errors="replace").split("\r\n")
        body = raw[end + 4:]
        try:
            status = int(head[0].split(" ", 2)[1])
        except (IndexError, ValueError):
            status = 0
        headers = {}
        for line in head[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        if headers.get("transfer-encoding", "").lower() == "chunked":
            body = FallbackBackend._dechunk(body)
        return status, headers, body

    @staticmethod
    def _dechunk(data: bytes) -> bytes:
        out = bytearray()
        idx = 0
        while idx < len(data):
            line_end = data.find(b"\r\n", idx)
            if line_end < 0:
                break
            try:
                size = int(data[idx:line_end].split(b";", 1)[0], 16)
            except ValueError:
                break
            if size == 0:
                break
            idx = line_end + 2
            out.extend(data[idx:idx + size])
            idx += size + 2
        return bytes(out)
