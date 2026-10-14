"""
Transport tests against a local aiohttp server, for both HTTP backends.
"""

import json

import pytest
import pytest_asyncio
from aiohttp import web

from tripo3d._http import AioHttpBackend, FallbackBackend
from tripo3d.exceptions import TripoAPIError, TripoRequestError

API_KEY = "tsk_transport"


@pytest_asyncio.fixture
async def server():
    state = {"hits": {}, "headers": {}, "bodies": {}}

    def record(request, name, body=None):
        state["hits"][name] = state["hits"].get(name, 0) + 1
        state["headers"][name] = dict(request.headers)
        state["bodies"][name] = body

    async def ok(request):
        record(request, "ok")
        return web.json_response({"code": 0, "status": "success", "data": {"value": request.query.get("q")}})

    async def business_error(request):
        record(request, "business_error")
        return web.json_response({"code": 1004, "status": "error", "message": "invalid model",
                                  "suggestion": "use v3.0", "request_id": "req-1"}, status=400)

    async def envelope_error_200(request):
        record(request, "envelope_error_200")
        return web.json_response({"code": 2010, "message": "Insufficient credits"})

    async def plain_502(request):
        record(request, "plain_502")
        return web.Response(status=502, text="<html>bad gateway</html>")

    async def flaky(request):
        record(request, "flaky")
        if state["hits"]["flaky"] < 3:
            return web.Response(status=429, headers={"Retry-After": "0"}, text="slow down")
        return web.json_response({"code": 0, "data": {"attempt": state["hits"]["flaky"]}})

    async def create(request):
        record(request, "create", await request.json())
        return web.Response(status=503, text="unavailable")

    async def upload(request):
        reader = await request.multipart()
        part = await reader.next()
        content = await part.read()
        record(request, "upload", {"name": part.name, "filename": part.filename, "size": len(content)})
        return web.json_response({"code": 0, "data": {"file_token": "file_up"}})

    async def put(request):
        record(request, "put", await request.read())
        return web.Response(status=200)

    async def download(request):
        record(request, "download")
        return web.Response(body=b"glTF" + b"x" * 2048)

    async def download_404(request):
        record(request, "download_404")
        return web.Response(status=404)

    app = web.Application()
    app.router.add_get("/ok", ok)
    app.router.add_post("/business_error", business_error)
    app.router.add_get("/envelope_error_200", envelope_error_200)
    app.router.add_get("/plain_502", plain_502)
    app.router.add_get("/flaky", flaky)
    app.router.add_post("/create", create)
    app.router.add_post("/v3/files", upload)
    app.router.add_put("/put", put)
    app.router.add_get("/download/m.glb", download)
    app.router.add_get("/download_404", download_404)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    state["base"] = f"http://127.0.0.1:{port}"
    yield state
    await runner.cleanup()


@pytest_asyncio.fixture(params=[AioHttpBackend, FallbackBackend], ids=["aiohttp", "fallback"])
async def backend(request, server):
    instance = request.param(API_KEY, server["base"])
    yield instance
    await instance.close()


@pytest.mark.asyncio
async def test_success_unwraps_data_and_sends_auth(backend, server):
    assert await backend.request("GET", "/ok", params={"q": "1", "skip": None}) == {"value": "1"}
    headers = server["headers"]["ok"]
    assert headers["Authorization"] == f"Bearer {API_KEY}"
    assert headers["User-Agent"].startswith("tripo3d-python/")


@pytest.mark.asyncio
async def test_business_error_maps_to_api_error(backend):
    with pytest.raises(TripoAPIError) as info:
        await backend.request("POST", "/business_error", json_data={})
    assert info.value.code == 1004
    assert info.value.suggestion == "use v3.0"
    assert info.value.request_id == "req-1"


@pytest.mark.asyncio
async def test_non_zero_code_with_http_200(backend):
    with pytest.raises(TripoAPIError) as info:
        await backend.request("GET", "/envelope_error_200")
    assert info.value.code == 2010


@pytest.mark.asyncio
async def test_plain_http_error_maps_to_request_error_after_get_retries(backend, server):
    with pytest.raises(TripoRequestError) as info:
        await backend.request("GET", "/plain_502")
    assert info.value.status_code == 502
    assert server["hits"]["plain_502"] == 3


@pytest.mark.asyncio
async def test_get_retries_on_429_then_succeeds(backend, server):
    assert await backend.request("GET", "/flaky") == {"attempt": 3}
    assert server["hits"]["flaky"] == 3


@pytest.mark.asyncio
async def test_post_is_never_retried(backend, server):
    with pytest.raises(TripoRequestError):
        await backend.request("POST", "/create", json_data={"prompt": "x"})
    assert server["hits"]["create"] == 1
    assert server["bodies"]["create"] == {"prompt": "x"}


@pytest.mark.asyncio
async def test_connection_error_is_request_error():
    dead = AioHttpBackend(API_KEY, "http://127.0.0.1:9")
    try:
        with pytest.raises(TripoRequestError):
            await dead.request("POST", "/x", json_data={})
    finally:
        await dead.close()


@pytest.mark.asyncio
async def test_multipart_upload(backend, server, tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG" + b"0" * 100)
    assert await backend.upload_multipart("/v3/files", str(path)) == {"file_token": "file_up"}
    assert server["bodies"]["upload"] == {"name": "file", "filename": "image.png", "size": 104}
    assert server["headers"]["upload"]["Authorization"] == f"Bearer {API_KEY}"


@pytest.mark.asyncio
async def test_presigned_put_and_download_never_send_api_key(backend, server, tmp_path):
    src = tmp_path / "big.glb"
    src.write_bytes(b"glTF-binary")
    await backend.put_file(server["base"] + "/put?X-Amz-Signature=abc", str(src), "model/gltf-binary")
    assert server["bodies"]["put"] == b"glTF-binary"
    assert "Authorization" not in server["headers"]["put"]

    dest = tmp_path / "out" / "m.glb"
    await backend.download_file(server["base"] + "/download/m.glb", str(dest))
    assert dest.read_bytes().startswith(b"glTF")
    assert "Authorization" not in server["headers"]["download"]


@pytest.mark.asyncio
async def test_download_http_error(backend, server, tmp_path):
    with pytest.raises(TripoRequestError) as info:
        await backend.download_file(server["base"] + "/download_404", str(tmp_path / "x"))
    assert info.value.status_code == 404


@pytest.mark.asyncio
async def test_aiohttp_sessions_are_closed_without_client_close(server, tmp_path, monkeypatch):
    import aiohttp

    created = []
    original = aiohttp.ClientSession

    class Recording(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(aiohttp, "ClientSession", Recording)
    backend = AioHttpBackend(API_KEY, server["base"])
    src = tmp_path / "a.png"
    src.write_bytes(b"\x89PNG")
    await backend.request("GET", "/ok")
    await backend.upload_multipart("/v3/files", str(src))
    await backend.put_file(server["base"] + "/put", str(src), "image/png")
    await backend.download_file(server["base"] + "/download/m.glb", str(tmp_path / "m.glb"))
    with pytest.raises(TripoAPIError):
        await backend.request("POST", "/business_error", json_data={})
    assert len(created) == 5
    assert all(session.closed for session in created)


def test_parse_envelope_passthrough():
    assert AioHttpBackend.parse_envelope({"x": 1}) == {"x": 1}
    assert AioHttpBackend.parse_envelope([1]) == [1]
    with pytest.raises(TripoAPIError):
        AioHttpBackend.parse_envelope({"status": "error", "message": json.dumps("x")})
