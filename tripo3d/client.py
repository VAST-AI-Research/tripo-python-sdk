"""
Tripo 3D Generation API Client.

All calls go to apiv3 (``https://openapi.tripo3d.ai`` / ``https://openapi.tripo3d.com``).
Method names, parameter names and return types of 0.x are kept, so existing callers
(including ComfyUI-Tripo <= 1.3.x) keep working after the v2 shutdown.
"""

import os
import asyncio
import inspect
import mimetypes
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from ._http import HttpBackend, create_http_backend
from .exceptions import TripoRequestError, TripoPollTimeoutError, TripoValidationError
from .inputs import FILE_TOKEN, LOCAL_FILE, InputLike, classify, looks_like_path
from .models import (
    Animation,
    Balance,
    BatchTaskResult,
    PostStyle,
    PresignedUpload,
    RigSpec,
    RigType,
    Task,
    TaskStatus,
    TaskUsageItem,
)

BASE_URL_GLOBAL = "https://openapi.tripo3d.ai"
BASE_URL_CN = "https://openapi.tripo3d.com"

# v2 accepted these and rewrote them before dispatch; apiv3 rejects them.
_LEGACY_RIG_MODEL_VERSIONS = {"v2.0-20250506": "v2.5-20260210"}  # openapi-server animate.go
# apiv3 /v3/mesh/decimate only accepts v1.0 / v2.0 / v3.0 (ModelPostProcessValidation.ALLOWED_DECIMATE_MODELS).
_LEGACY_LOWPOLY_MODEL_VERSIONS = {
    "P-v1.0-20250506": "v1.0",
    "P-v2.0-20251225": "v2.0",
    "P-v2.0-20251226": "v2.0",
    "P-v3.0-20260909": "v3.0",
}

# v2 ``type`` -> apiv3 route, for callers that still use ``create_task``.
_CREATE_TASK_ROUTES = {
    "text_to_model": "/v3/generation/text-to-model",
    "image_to_model": "/v3/generation/image-to-model",
    "multiview_to_model": "/v3/generation/multiview-to-model",
    "text_to_image": "/v3/generation/text-to-image",
    "generate_image": "/v3/generation/image-to-image",
    "generate_multiview_image": "/v3/generation/image-to-multiview",
    "edit_multiview_image": "/v3/generation/edit-multiview",
    "image_to_splat": "/v3/generation/image-to-splat",
    "image_to_depth": "/v3/generation/image-to-depth",
    "texture_model": "/v3/models/texture",
    "convert_model": "/v3/models/convert",
    "import_model": "/v3/models/import",
    "animate_prerigcheck": "/v3/animations/rig-check",
    "animate_rig": "/v3/animations/rig",
    "animate_retarget": "/v3/animations/retarget",
    "mesh_segmentation": "/v3/mesh/segment",
    "mesh_completion": "/v3/mesh/complete",
    "highpoly_to_lowpoly": "/v3/mesh/decimate",
    "mesh_uv": "/v3/mesh/uv",
}

_RETIRED_TASK_TYPES = {"refine_model", "stylize_model"}
_RETIRED = ("{name} is no longer supported: Tripo has retired this capability. "
            "Remove it from your code or workflow (no request was sent).")

_IMAGE_FIELDS = {"rendered_image", "image", "front_view", "left_view", "back_view", "right_view",
                 "uv_render", "depth_image"}
_VIDEO_FIELDS = {"rendered_video"}


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _deprecated(message: str) -> None:
    warnings.warn(message, DeprecationWarning, stacklevel=3)


class TripoClient:
    """Async client for the Tripo apiv3 API."""

    SEGMENT_V2_MODEL = "v2.0-20260430"
    # Larger files go through a presigned PUT; /v3/files itself caps at 150 MB.
    MULTIPART_MAX_BYTES = 50 * 1024 * 1024

    def __init__(
        self,
        api_key: Optional[str] = None,
        IS_GLOBAL: bool = True,
        v3_base_url: Optional[str] = None,
        verify_ssl: bool = True,
    ):
        """
        Initialize the Tripo API client.

        Args:
            api_key: The API key for authentication. If not provided, it will be read from the
                     TRIPO_API_KEY environment variable.
            IS_GLOBAL: True for the global endpoint (openapi.tripo3d.ai), False for China
                       (openapi.tripo3d.com).
            v3_base_url: Override the endpoint, e.g. a staging host.
            verify_ssl: Verify TLS certificates for API calls.

        Raises:
            ValueError: If no API key is provided or the key does not start with ``tsk_``.
        """
        self.api_key = api_key or os.environ.get("TRIPO_API_KEY")
        if not self.api_key:
            raise TripoValidationError(
                "API key is required. Provide it as an argument or set the TRIPO_API_KEY environment variable."
            )
        if not self.api_key.startswith('tsk_'):
            raise TripoValidationError("API key must start with 'tsk_'")

        default_base = BASE_URL_GLOBAL if IS_GLOBAL else BASE_URL_CN
        self.BASE_URL = (v3_base_url or default_base).rstrip("/")
        self._v3_base_url = self.BASE_URL
        self._http: HttpBackend = create_http_backend(self.api_key, self.BASE_URL, verify_ssl=verify_ssl)

    async def close(self) -> None:
        """Close any open connections."""
        await self._http.close()

    async def __aenter__(self) -> 'TripoClient':
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _non_default(self, method_name: str, values: Dict[str, Any]) -> Dict[str, Any]:
        """Keep values that are set and differ from the method's declared default.

        0.x only sent arguments that differed from the signature default and left the rest to
        the server; apiv3 server defaults match those signatures, so the wire stays identical.
        """
        params = inspect.signature(getattr(type(self), method_name)).parameters
        out: Dict[str, Any] = {}
        for name, value in values.items():
            if value is None:
                continue
            param = params.get(name)
            if param is not None and param.default is not inspect.Parameter.empty and value == param.default:
                continue
            out[name] = _enum_value(value)
        return out

    @staticmethod
    def _merge_extra(payload: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in extra.items():
            if value is None:
                continue
            if key in payload:
                raise TripoValidationError(f"parameter '{key}' is given twice")
            payload[key] = _enum_value(value)
        return payload

    async def _resolve_input(self, value: InputLike) -> str:
        """Turn a URL / file_token / task_id / local path into an apiv3 ``input`` string."""
        if value is None or not str(value).strip():
            raise TripoValidationError("input must be a non-empty URL, file_token, task_id or local file path")
        kind = classify(value)
        if kind == LOCAL_FILE:
            return (await self.upload_file(str(value)))["file_token"]
        text = str(value).strip()
        if kind == FILE_TOKEN and looks_like_path(text):
            raise FileNotFoundError(f"File not found: {text}")
        return text

    async def _submit(self, path: str, payload: Dict[str, Any]) -> str:
        data = await self._http.request("POST", path, json_data=payload)
        task_id = data.get("task_id") if isinstance(data, dict) else None
        if not task_id:
            raise TripoRequestError(0, f"Unexpected create response from {path}: {data!r}")
        return str(task_id)

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    async def get_task(self, task_id: str, *, use_v3: bool = True, step: Optional[int] = None) -> Task:
        """
        Get the status of a task (``GET /v3/tasks/{task_id}``).

        Args:
            task_id: The ID of the task to get.
            use_v3: Ignored; every task is queried on apiv3. Kept for 0.x callers.
            step: Pass 1 to include ``pipeline_step`` details.
        """
        data = await self._http.request(
            "GET", f"/v3/tasks/{task_id}", params={"step": step} if step is not None else None
        )
        if not isinstance(data, dict):
            raise TripoRequestError(0, f"Unexpected task response: {data!r}")
        return Task.from_dict(data)

    async def list_tasks(self, task_ids: Sequence[str]) -> BatchTaskResult:
        """Query several tasks at once (``POST /v3/tasks/list``)."""
        if not task_ids:
            raise TripoValidationError("task_ids must not be empty")
        data = await self._http.request("POST", "/v3/tasks/list", json_data={"task_ids": list(task_ids)})
        return BatchTaskResult.from_dict(data if isinstance(data, dict) else {})

    get_tasks = list_tasks

    async def create_task(self, task_data: Dict[str, Any]) -> str:
        """
        Create a task from a 0.x-style payload ``{"type": ..., ...}``.

        The ``type`` selects the apiv3 route; the remaining fields are sent as-is (apiv3 accepts
        the v2 field names such as ``file`` / ``original_model_task_id``).
        """
        body = dict(task_data)
        task_type = body.pop("type", None)
        if task_type in _RETIRED_TASK_TYPES:
            raise TripoValidationError(_RETIRED.format(name=task_type))
        path = _CREATE_TASK_ROUTES.get(task_type)
        if path is None:
            raise TripoValidationError(f"unsupported task type for apiv3: {task_type!r}")
        return await self._submit(path, body)

    async def wait_for_task(
        self,
        task_id: str,
        polling_interval: float = 2.0,
        timeout: Optional[float] = None,
        verbose: bool = False,
        use_v3: bool = True,
    ) -> Task:
        """
        Wait for a task to reach a terminal status.

        Args:
            task_id: The ID of the task to wait for.
            polling_interval: Initial polling interval in seconds (grows up to 30s).
            timeout: Maximum seconds to wait; None waits indefinitely.
            verbose: Print progress while polling.
            use_v3: Ignored; kept for 0.x callers.

        Raises:
            TripoPollTimeoutError: (an ``asyncio.TimeoutError``) when ``timeout`` elapses.
        """
        start_time = time.monotonic()
        interval = max(float(polling_interval), 0.1)
        while True:
            task = await self.get_task(task_id)
            if task.status.is_terminal():
                if verbose:
                    print(f"\nTask {task_id} {task.status.value} in {time.monotonic() - start_time:.1f} seconds")
                return task

            if verbose:
                progress = max(0, min(int(task.progress or 0), 100))
                bar = f"[{'=' * (progress // 5)}{' ' * (20 - progress // 5)}] {progress}%"
                print(f"\rTask {task_id} is {task.status.value}. Progress: {bar}", end='', flush=True)

            sleep_for = interval
            if timeout is not None:
                remaining = timeout - (time.monotonic() - start_time)
                if remaining <= 0:
                    raise TripoPollTimeoutError(task_id=task_id, timeout_seconds=timeout)
                sleep_for = min(sleep_for, remaining)
            await asyncio.sleep(sleep_for)
            interval = min(interval * 2, 30.0)

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_balance(self) -> Balance:
        """Get the account balance (``GET /v3/account/balance``)."""
        data = await self._http.request("GET", "/v3/account/balance")
        return Balance.from_dict(data if isinstance(data, dict) else {})

    async def get_usage(self, limit: int = 50, offset: int = 0) -> List[TaskUsageItem]:
        """List recent task usage (``GET /v3/account/usage``)."""
        data = await self._http.request("GET", "/v3/account/usage", params={"limit": limit, "offset": offset})
        items = data.get("items") if isinstance(data, dict) else data
        return [TaskUsageItem.from_dict(item) for item in (items or []) if isinstance(item, dict)]

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    async def presign_upload(self, format: str) -> PresignedUpload:
        """Request a presigned PUT URL (``POST /v3/files/presign``)."""
        data = await self._http.request("POST", "/v3/files/presign", json_data={"format": format.lstrip(".").lower()})
        result = PresignedUpload.from_dict(data if isinstance(data, dict) else {})
        if not result.upload_url or not result.file_token:
            raise TripoRequestError(0, f"Incomplete presign response: {data!r}")
        return result

    async def upload_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Upload a local file and return ``{"file_token": "file_..."}``.

        Files up to 50 MB use ``POST /v3/files``; larger files use a presigned PUT
        (``POST /v3/files/presign``). The API caps uploads at 150 MB.

        Raises:
            FileNotFoundError: If the file doesn't exist.
        """
        path = str(file_path)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")

        if os.path.getsize(path) <= self.MULTIPART_MAX_BYTES:
            data = await self._http.upload_multipart("/v3/files", path, field_name="file")
            token = data.get("file_token") if isinstance(data, dict) else None
            if not token:
                raise TripoRequestError(0, f"Upload response missing file_token: {data!r}")
            return {"file_token": str(token)}

        ext = os.path.splitext(path)[1].lstrip(".").lower()
        if not ext:
            raise TripoValidationError(f"Cannot determine file format from extension: {path}")
        presigned = await self.presign_upload(ext)
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        await self._http.put_file(presigned.upload_url, path, content_type)
        return {"file_token": presigned.file_token}

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    @staticmethod
    def _is_ssl_error(error: Exception) -> bool:
        text = str(error).lower()
        return any(marker in text for marker in (
            'ssl certificate verification error',
            'certificate_verify_failed',
            'unable to get local issuer certificate',
            'sslcertverificationerror',
        ))

    async def _download_with_ssl_retry(self, url: str, output_path: str) -> None:
        try:
            await self._http.download_file(url, output_path)
        except Exception as e:
            if not self._is_ssl_error(e):
                raise
            warnings.warn(
                "SSL certificate verification failed during download. Retrying with SSL verification "
                "disabled. Consider updating your system's certificate store.",
                UserWarning,
            )
            insecure = create_http_backend(self.api_key, self.BASE_URL, verify_ssl=False)
            try:
                await insecure.download_file(url, output_path)
            finally:
                await insecure.close()

    async def download_file(self, url: str, output_path: Union[str, Path]) -> None:
        """Download a signed result URL to ``output_path`` (no API key is sent)."""
        await self._download_with_ssl_retry(url, str(output_path))

    async def download_task_models(self, task: Task, output_dir: str) -> Dict[str, Optional[str]]:
        """
        Download the files of a successful task.

        Returns a dict keyed by output field (``model`` first). apiv3 returns a single model URL;
        ``pbr_model`` points at the same downloaded file instead of fetching it twice. A field
        whose download failed maps to ``None``.

        Raises:
            ValueError: If the task is not successful.
            FileNotFoundError: If output_dir doesn't exist.
        """
        if task.status != TaskStatus.SUCCESS:
            raise ValueError(f"Cannot download files from task with status: {task.status}")
        if not os.path.exists(output_dir):
            raise FileNotFoundError(f"Output directory not found: {output_dir}")

        out = task.output
        fields = [
            ("model", out.model_url or out.model, "_model"),
            ("base_model", out.base_model, "_base"),
            ("pbr_model", out.pbr_model, "_pbr"),
            ("rendered_image", out.rendered_image, "_rendered"),
            ("image", out.image, "_image"),
            ("front_view", out.front_view_url, "_front"),
            ("left_view", out.left_view_url, "_left"),
            ("back_view", out.back_view_url, "_back"),
            ("right_view", out.right_view_url, "_right"),
            ("uv_render", out.uv_render_url, "_uv_render"),
            ("depth_image", out.depth_image_url, "_depth"),
            ("rendered_video", out.rendered_video_url, "_video"),
        ]

        def extension(url: str, field_name: str) -> str:
            ext = os.path.splitext(url.split('?')[0].split('/')[-1])[1]
            if ext:
                return ext
            if field_name in _IMAGE_FIELDS:
                return '.jpg'
            if field_name in _VIDEO_FIELDS:
                return '.mp4'
            return '.glb'

        by_url: Dict[str, str] = {}
        aliases: List[tuple] = []
        jobs: List[tuple] = []
        for field_name, url, suffix in fields:
            if not url:
                continue
            if url in by_url:
                aliases.append((field_name, by_url[url]))
                continue
            by_url[url] = field_name
            path = os.path.join(output_dir, f"{task.task_id}{suffix}{extension(url, field_name)}")
            jobs.append((field_name, url, path))

        results = await asyncio.gather(
            *(self._download_with_ssl_retry(url, path) for _, url, path in jobs),
            return_exceptions=True,
        )
        downloaded: Dict[str, Optional[str]] = {}
        for (field_name, _, path), outcome in zip(jobs, results):
            downloaded[field_name] = None if isinstance(outcome, Exception) else path
        for field_name, source in aliases:
            downloaded[field_name] = downloaded.get(source)
        return {name: downloaded[name] for name, _, _ in fields if name in downloaded}

    async def download_rendered_image(
        self, task: Task, output_dir: str, filename: Optional[str] = None
    ) -> Optional[str]:
        """Download the rendered preview image of a successful task, or return None if absent."""
        if task.status != TaskStatus.SUCCESS:
            raise ValueError(f"Cannot download files from task with status: {task.status}")
        if not os.path.exists(output_dir):
            raise FileNotFoundError(f"Output directory not found: {output_dir}")
        url = task.output.rendered_image
        if not url:
            return None
        ext = os.path.splitext(url.split('?')[0].split('/')[-1])[1] or '.jpg'
        output_path = os.path.join(output_dir, filename or f"{task.task_id}_rendered{ext}")
        await self._download_with_ssl_retry(url, output_path)
        return output_path

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def text_to_model(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        model_version: str = "v2.5-20250123",
        face_limit: Optional[int] = None,
        texture: Optional[bool] = True,
        pbr: Optional[bool] = True,
        image_seed: Optional[int] = None,
        model_seed: Optional[int] = None,
        texture_seed: Optional[int] = None,
        texture_quality: Optional[str] = "standard",
        geometry_quality: Optional[str] = "standard",
        auto_size: Optional[bool] = False,
        quad: Optional[bool] = False,
        compress: Optional[bool] = False,
        generate_parts: Optional[bool] = False,
        smart_low_poly: Optional[bool] = False,
        export_uv: Optional[bool] = True,
        **kwargs: Any,
    ) -> str:
        """
        Create a text to 3D model task (``POST /v3/generation/text-to-model``).

        Extra keyword arguments (e.g. ``texture_version``, ``export_orientation``) are sent as-is.

        Returns:
            The task ID.
        """
        if not prompt:
            raise TripoValidationError("Prompt is required.")
        payload: Dict[str, Any] = {"prompt": prompt, "model": model_version}
        payload.update(self._non_default("text_to_model", {
            "negative_prompt": negative_prompt, "face_limit": face_limit, "texture": texture, "pbr": pbr,
            "image_seed": image_seed, "model_seed": model_seed, "texture_seed": texture_seed,
            "texture_quality": texture_quality, "geometry_quality": geometry_quality, "auto_size": auto_size,
            "quad": quad, "generate_parts": generate_parts, "smart_low_poly": smart_low_poly,
            "export_uv": export_uv,
        }))
        if compress:
            payload["compress"] = "geometry"
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/generation/text-to-model", payload)

    async def image_to_model(
        self,
        image: InputLike,
        model_version: str = "v2.5-20250123",
        face_limit: Optional[int] = None,
        texture: Optional[bool] = True,
        pbr: Optional[bool] = True,
        model_seed: Optional[int] = None,
        texture_seed: Optional[int] = None,
        texture_quality: Optional[str] = "standard",
        geometry_quality: Optional[str] = "standard",
        texture_alignment: Optional[str] = "original_image",
        auto_size: Optional[bool] = False,
        orientation: Optional[str] = "default",
        quad: Optional[bool] = False,
        compress: Optional[bool] = False,
        generate_parts: Optional[bool] = False,
        smart_low_poly: Optional[bool] = False,
        enable_image_autofix: Optional[bool] = False,
        export_uv: Optional[bool] = True,
        **kwargs: Any,
    ) -> str:
        """
        Create an image to 3D model task (``POST /v3/generation/image-to-model``).

        Args:
            image: A local image path, an image URL, a ``file_token`` or the task_id of an
                   image-producing task.

        Returns:
            The task ID.
        """
        payload: Dict[str, Any] = {"input": await self._resolve_input(image), "model": model_version}
        payload.update(self._non_default("image_to_model", {
            "face_limit": face_limit, "texture": texture, "pbr": pbr, "model_seed": model_seed,
            "texture_seed": texture_seed, "texture_quality": texture_quality,
            "geometry_quality": geometry_quality, "texture_alignment": texture_alignment,
            "auto_size": auto_size, "orientation": orientation, "quad": quad,
            "generate_parts": generate_parts, "smart_low_poly": smart_low_poly,
            "enable_image_autofix": enable_image_autofix, "export_uv": export_uv,
        }))
        if compress:
            payload["compress"] = "geometry"
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/generation/image-to-model", payload)

    async def multiview_to_model(
        self,
        images: Union[Sequence[Optional[InputLike]], str],
        model_version: str = "v2.5-20250123",
        face_limit: Optional[int] = None,
        texture: Optional[bool] = True,
        pbr: Optional[bool] = True,
        model_seed: Optional[int] = None,
        texture_seed: Optional[int] = None,
        texture_quality: Optional[str] = "standard",
        geometry_quality: Optional[str] = "standard",
        texture_alignment: Optional[str] = "original_image",
        auto_size: Optional[bool] = False,
        orientation: Optional[str] = "default",
        quad: Optional[bool] = False,
        compress: Optional[bool] = False,
        generate_parts: Optional[bool] = False,
        smart_low_poly: Optional[bool] = False,
        export_uv: Optional[bool] = True,
        **kwargs: Any,
    ) -> str:
        """
        Create a 3D model from multiple views (``POST /v3/generation/multiview-to-model``).

        Args:
            images: ``[front, left, back, right]``; a missing view may be ``None``. Each entry is a
                    local path, URL or ``file_token``. Alternatively pass the task_id of a finished
                    ``generate_multiview_image`` task as a plain string.

        Returns:
            The task ID.
        """
        if isinstance(images, str):
            inputs: List[Any] = [{"task_id": images}]
        else:
            inputs = [None if item is None else await self._resolve_input(item) for item in images]
            if not inputs or inputs[0] is None:
                raise TripoValidationError("the front view (images[0]) is required")
        payload: Dict[str, Any] = {"inputs": inputs, "model": model_version}
        payload.update(self._non_default("multiview_to_model", {
            "face_limit": face_limit, "texture": texture, "pbr": pbr, "model_seed": model_seed,
            "texture_seed": texture_seed, "texture_quality": texture_quality,
            "geometry_quality": geometry_quality, "texture_alignment": texture_alignment,
            "auto_size": auto_size, "orientation": orientation, "quad": quad,
            "generate_parts": generate_parts, "smart_low_poly": smart_low_poly, "export_uv": export_uv,
        }))
        if compress:
            payload["compress"] = "geometry"
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/generation/multiview-to-model", payload)

    async def text_to_image(self, prompt: str, negative_prompt: Optional[str] = None, **kwargs: Any) -> str:
        """
        Create a text-to-image task (``POST /v3/generation/text-to-image``).

        Extra keyword arguments such as ``model``, ``size``, ``aspect_ratio`` or ``output_format``
        are sent as-is.
        """
        if not prompt:
            raise TripoValidationError("Prompt is required.")
        payload: Dict[str, Any] = {"prompt": prompt}
        if negative_prompt is not None:
            payload["negative_prompt"] = negative_prompt
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/generation/text-to-image", payload)

    async def image_to_image(
        self,
        input: Optional[InputLike] = None,
        *,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
        inputs: Optional[Sequence[InputLike]] = None,
        **kwargs: Any,
    ) -> str:
        """Transform one or more reference images (``POST /v3/generation/image-to-image``)."""
        payload: Dict[str, Any] = {}
        if input is not None:
            payload["input"] = await self._resolve_input(input)
        if inputs is not None:
            payload["inputs"] = [await self._resolve_input(item) for item in inputs]
        if not payload:
            raise TripoValidationError("input or inputs is required")
        if prompt is not None:
            payload["prompt"] = prompt
        if model is not None:
            payload["model"] = model
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/generation/image-to-image", payload)

    async def generate_image(
        self,
        prompt: Optional[str] = None,
        model_version: Optional[str] = None,
        file: Optional[InputLike] = None,
        files: Optional[List[InputLike]] = None,
        template: Optional[str] = None,
        t_pose: Optional[bool] = False,
        sketch_to_render: Optional[bool] = False,
        **kwargs: Any,
    ) -> str:
        """
        Image generation with reference images and templates (apiv3 ``image-to-image``).

        Args:
            prompt: Text instruction. Optional when ``template`` and ``file`` are both provided.
            model_version: Image model; None lets the server choose its default.
            file: Single reference image (path / URL / file_token / task_id).
            files: Multiple reference images.
            template: Image template slug (e.g. "t-pose").
            t_pose: Transform the subject to a T-pose.
            sketch_to_render: Render a sketch.
        """
        extra = self._non_default("generate_image", {
            "template": template, "t_pose": t_pose, "sketch_to_render": sketch_to_render,
        })
        extra.update(kwargs)
        return await self.image_to_image(file, prompt=prompt, model=model_version, inputs=files, **extra)

    async def image_to_multiview(self, input: InputLike, **kwargs: Any) -> str:
        """Generate front/left/back/right views (``POST /v3/generation/image-to-multiview``)."""
        payload: Dict[str, Any] = {"input": await self._resolve_input(input)}
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/generation/image-to-multiview", payload)

    async def generate_multiview_image(self, image: InputLike, **kwargs: Any) -> str:
        """Generate four views from a single image; same as :meth:`image_to_multiview`."""
        return await self.image_to_multiview(image, **kwargs)

    async def edit_multiview(self, input: str, prompts: List[Dict[str, str]], **kwargs: Any) -> str:
        """Edit views of an ``image_to_multiview`` task (``POST /v3/generation/edit-multiview``)."""
        payload: Dict[str, Any] = {"input": input, "prompts": list(prompts)}
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/generation/edit-multiview", payload)

    async def edit_multiview_image(self, original_task_id: str, prompts: List[Dict[str, str]]) -> str:
        """Edit views of a multiview task; same as :meth:`edit_multiview`."""
        return await self.edit_multiview(original_task_id, prompts)

    async def image_to_splat(self, image: InputLike, model_seed: Optional[int] = None, **kwargs: Any) -> str:
        """Generate a Gaussian splat from an image (``POST /v3/generation/image-to-splat``)."""
        payload: Dict[str, Any] = {"input": await self._resolve_input(image)}
        if model_seed is not None:
            payload["model_seed"] = model_seed
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/generation/image-to-splat", payload)

    async def image_to_depth(
        self,
        image: InputLike,
        kind: Optional[str] = None,
        process_res: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """
        Estimate a depth map from an image (``POST /v3/generation/image-to-depth``).

        Args:
            kind: ``gray`` (server default) or ``color``.
            process_res: Processing resolution, 126-2016 (server default 504).
        """
        payload: Dict[str, Any] = {"input": await self._resolve_input(image)}
        if kind is not None:
            payload["kind"] = kind
        if process_res is not None:
            payload["process_res"] = process_res
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/generation/image-to-depth", payload)

    # ------------------------------------------------------------------
    # Model post-processing
    # ------------------------------------------------------------------

    async def import_model(self, file: InputLike, **kwargs: Any) -> str:
        """
        Import an external 3D model (``POST /v3/models/import``).

        Args:
            file: A local model file (uploaded first), a model URL, or a ``file_token``.
        """
        payload: Dict[str, Any] = {"input": await self._resolve_input(file)}
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/models/import", payload)

    async def convert_model(
        self,
        original_model_task_id: str,
        format: str,
        quad: Optional[bool] = False,
        force_symmetry: Optional[bool] = False,
        face_limit: Optional[int] = None,
        flatten_bottom: Optional[bool] = False,
        flatten_bottom_threshold: Optional[float] = 0.01,
        texture_size: Optional[int] = 4096,
        texture_format: Optional[str] = "JPEG",
        scale_factor: Optional[float] = 1.0,
        pivot_to_center_bottom: Optional[bool] = False,
        with_animation: Optional[bool] = True,
        pack_uv: Optional[bool] = False,
        bake: Optional[bool] = True,
        part_names: Optional[List[str]] = None,
        export_vertex_colors: Optional[bool] = False,
        fbx_preset: Optional[str] = "blender",
        export_orientation: Optional[str] = "+x",
        animate_in_place: Optional[bool] = False,
        **kwargs: Any,
    ) -> str:
        """
        Convert a model to another format (``POST /v3/models/convert``).

        ``face_limit`` values <= 0 mean "no limit" and are not sent.
        """
        payload: Dict[str, Any] = {"input": original_model_task_id, "format": format}
        payload.update(self._non_default("convert_model", {
            "quad": quad, "force_symmetry": force_symmetry,
            "face_limit": face_limit if face_limit is not None and face_limit > 0 else None,
            "flatten_bottom": flatten_bottom, "flatten_bottom_threshold": flatten_bottom_threshold,
            "texture_size": texture_size, "texture_format": texture_format, "scale_factor": scale_factor,
            "pivot_to_center_bottom": pivot_to_center_bottom, "with_animation": with_animation,
            "pack_uv": pack_uv, "bake": bake, "part_names": part_names or None,
            "export_vertex_colors": export_vertex_colors, "fbx_preset": fbx_preset,
            "export_orientation": export_orientation, "animate_in_place": animate_in_place,
        }))
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/models/convert", payload)

    async def texture_model(
        self,
        original_model_task_id: str,
        texture: Optional[bool] = True,
        pbr: Optional[bool] = True,
        model_seed: Optional[int] = None,
        texture_seed: Optional[int] = None,
        texture_quality: Optional[str] = "standard",
        texture_alignment: Optional[str] = "original_image",
        part_names: Optional[List[str]] = None,
        compress: Optional[bool] = False,
        bake: Optional[bool] = True,
        text_prompt: Optional[str] = None,
        image_prompt: Optional[InputLike] = None,
        style_image: Optional[InputLike] = None,
        model_version: Optional[str] = "v2.5-20250123",
        **kwargs: Any,
    ) -> str:
        """
        Generate a new texture for a model (``POST /v3/models/texture``).

        Args:
            original_model_task_id: Task ID of the model to texture (a model URL or file_token
                                    of an imported file also works).
            text_prompt / image_prompt / style_image: Texture guidance; images may be local
                                    paths, URLs or file_tokens.
            model_version: ``v2.5-20250123``, ``v3.0-20250812`` or ``v3.5-20260815``.

        Extra keyword arguments (e.g. ``delight``) are sent as-is.
        """
        payload: Dict[str, Any] = {"input": original_model_task_id}
        if model_version is not None:
            payload["model"] = model_version
        payload.update(self._non_default("texture_model", {
            "texture": texture, "pbr": pbr, "model_seed": model_seed, "texture_seed": texture_seed,
            "texture_quality": texture_quality, "texture_alignment": texture_alignment,
            "part_names": part_names or None, "bake": bake,
        }))
        if compress:
            payload["compress"] = "geometry"
        texture_prompt: Dict[str, Any] = {}
        if text_prompt:
            texture_prompt["text"] = text_prompt
        if image_prompt is not None:
            texture_prompt["image"] = await self._resolve_input(image_prompt)
        if style_image is not None:
            texture_prompt["style_image"] = await self._resolve_input(style_image)
        if texture_prompt:
            payload["texture_prompt"] = texture_prompt
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/models/texture", payload)

    async def refine_model(self, draft_model_task_id: str) -> str:
        """
        Removed: refine is no longer supported by Tripo. Always raises; no request is sent.

        Kept only so callers built for 0.x (e.g. ComfyUI-Tripo 1.3.x) get this explanation instead of
        an ``AttributeError``.
        """
        raise TripoValidationError(_RETIRED.format(name="refine_model"))

    async def stylize_model(
        self, original_model_task_id: str, style: Union[PostStyle, str], block_size: Optional[int] = 80
    ) -> str:
        """
        Removed: stylize is no longer supported by Tripo. Always raises; no request is sent.

        Kept only so callers built for 0.x (e.g. ComfyUI-Tripo 1.3.x) get this explanation instead of
        an ``AttributeError``.
        """
        raise TripoValidationError(_RETIRED.format(name="stylize_model"))

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    async def rig_check(self, input: str, **kwargs: Any) -> str:
        """Check whether a model can be rigged (``POST /v3/animations/rig-check``).

        The finished task reports ``output.riggable`` and ``output.rig_type``.
        """
        payload: Dict[str, Any] = {"input": input}
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/animations/rig-check", payload)

    async def check_riggable(self, original_model_task_id: str) -> str:
        """Check whether a model can be rigged; same as :meth:`rig_check`."""
        return await self.rig_check(original_model_task_id)

    async def rig(
        self,
        input: str,
        *,
        model: Optional[str] = None,
        rig_type: Optional[Union[RigType, str]] = None,
        spec: Optional[Union[RigSpec, str]] = None,
        out_format: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Rig a model (``POST /v3/animations/rig``).

        ``model``: ``v1.0-20240301`` (server default), ``v2.5-20260210`` or ``v3.0-20260909``.
        Extra keyword arguments (e.g. ``no_weights_list``) are sent as-is.
        """
        payload: Dict[str, Any] = {"input": input}
        if model is not None:
            if model in _LEGACY_RIG_MODEL_VERSIONS:
                replacement = _LEGACY_RIG_MODEL_VERSIONS[model]
                warnings.warn(
                    f"rig model {model} is retired on apiv3; using {replacement} as v2 did", UserWarning, stacklevel=2
                )
                model = replacement
            payload["model"] = model
        for key, value in (("rig_type", rig_type), ("spec", spec), ("out_format", out_format)):
            if value is not None:
                payload[key] = _enum_value(value)
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/animations/rig", payload)

    async def rig_model(
        self,
        original_model_task_id: str,
        model_version: Optional[str] = "v1.0-20240301",
        out_format: Optional[str] = "glb",
        rig_type: Optional[Union[RigType, str]] = RigType.BIPED,
        spec: Optional[Union[RigSpec, str]] = RigSpec.TRIPO,
        **kwargs: Any,
    ) -> str:
        """
        Rig a model for animation; see :meth:`rig`.

        ``model_version`` ``v2.0-20250506`` (retired) is sent as ``v2.5-20260210``, exactly as
        the v2 API did.
        """
        extra = self._non_default("rig_model", {"out_format": out_format, "rig_type": rig_type, "spec": spec})
        extra.update(kwargs)
        return await self.rig(original_model_task_id, model=model_version, **extra)

    async def retarget(
        self,
        input: str,
        *,
        animation: Optional[Union[Animation, str]] = None,
        animations: Optional[Sequence[Union[Animation, str]]] = None,
        out_format: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Apply preset animations to a rigged model (``POST /v3/animations/retarget``).

        Pass ``animation`` or up to 5 ``animations``. Extra keyword arguments
        (``export_with_geometry``, ``animate_in_place``, ``render_video`` ...) are sent as-is.
        """
        payload: Dict[str, Any] = {"input": input}
        if animation is not None:
            payload["animation"] = _enum_value(animation)
        if animations is not None:
            payload["animations"] = [_enum_value(item) for item in animations]
        if "animation" not in payload and "animations" not in payload:
            raise TripoValidationError("animation or animations is required")
        if out_format is not None:
            payload["out_format"] = out_format
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/animations/retarget", payload)

    async def retarget_animation(
        self,
        original_model_task_id: str,
        animation: Union[Animation, str, List[Union[Animation, str]]],
        out_format: Optional[str] = "glb",
        bake_animation: Optional[bool] = True,
        export_with_geometry: Optional[bool] = False,
        animate_in_place: Optional[bool] = False,
        **kwargs: Any,
    ) -> str:
        """
        Apply an animation to a rigged model; see :meth:`retarget`.

        ``animation`` may be a single preset or a list. ``bake_animation`` is accepted for
        compatibility but apiv3 no longer uses it, so it is not sent.
        """
        if bake_animation is False:
            _deprecated("bake_animation is ignored by apiv3 and will be removed in tripo3d 2.0.0")
        extra = self._non_default("retarget_animation", {
            "export_with_geometry": export_with_geometry, "animate_in_place": animate_in_place,
        })
        extra.update(kwargs)
        out = out_format if out_format != "glb" else None
        if isinstance(animation, (list, tuple)):
            return await self.retarget(original_model_task_id, animations=animation, out_format=out, **extra)
        return await self.retarget(original_model_task_id, animation=animation, out_format=out, **extra)

    # ------------------------------------------------------------------
    # Mesh
    # ------------------------------------------------------------------

    async def mesh_segment(
        self,
        input: str,
        *,
        model: Optional[str] = None,
        segmentation_granularity: Optional[str] = None,
        ref_image: Optional[InputLike] = None,
        split_by_connectivity: Optional[bool] = None,
        **kwargs: Any,
    ) -> str:
        """Segment a mesh (``POST /v3/mesh/segment``).

        ``model``: ``v1.0-20250506`` (server default) or ``v2.0-20260430``; ``ref_image`` and the
        other options are for v2.0 only.
        """
        payload: Dict[str, Any] = {"input": input}
        if model is not None:
            payload["model"] = model
        if segmentation_granularity:
            payload["segmentation_granularity"] = segmentation_granularity
        if ref_image is not None:
            payload["ref_image"] = await self._resolve_input(ref_image)
        if split_by_connectivity is not None:
            payload["split_by_connectivity"] = split_by_connectivity
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/mesh/segment", payload)

    async def mesh_segmentation(
        self,
        original_model_task_id: str,
        model_version: Optional[str] = "v1.0-20250506",
        segmentation_granularity: Optional[str] = None,
        ref_image: Optional[InputLike] = None,
        split_by_connectivity: Optional[bool] = None,
        **kwargs: Any,
    ) -> str:
        """Segment a 3D model; see :meth:`mesh_segment`."""
        return await self.mesh_segment(
            original_model_task_id,
            model=model_version,
            segmentation_granularity=segmentation_granularity,
            ref_image=ref_image,
            split_by_connectivity=split_by_connectivity,
            **kwargs,
        )

    async def mesh_complete(
        self,
        input: str,
        *,
        model: Optional[str] = None,
        part_names: Optional[Sequence[str]] = None,
        completion_mode: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Complete a segmented mesh (``POST /v3/mesh/complete``).

        ``input`` must be a ``mesh_segmentation`` task; ``completion_mode`` is ``ai_completion``
        or ``quick_cap``.
        """
        payload: Dict[str, Any] = {"input": input}
        if model is not None:
            payload["model"] = model
        if part_names:
            payload["part_names"] = list(part_names)
        if completion_mode is not None:
            payload["completion_mode"] = completion_mode
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/mesh/complete", payload)

    async def mesh_completion(
        self,
        original_model_task_id: str,
        model_version: Optional[str] = "v1.0-20250506",
        part_names: Optional[List[str]] = None,
        completion_mode: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Complete a segmented 3D model; see :meth:`mesh_complete`."""
        return await self.mesh_complete(
            original_model_task_id,
            model=model_version,
            part_names=part_names,
            completion_mode=completion_mode,
            **kwargs,
        )

    async def mesh_decimate(
        self,
        input: str,
        *,
        model: Optional[str] = None,
        face_limit: Optional[int] = None,
        quad: Optional[bool] = None,
        bake: Optional[bool] = None,
        part_names: Optional[Sequence[str]] = None,
        smart_uv: Optional[bool] = None,
        **kwargs: Any,
    ) -> str:
        """Retopologize / reduce faces (``POST /v3/mesh/decimate``).

        ``model``: ``v1.0``, ``v2.0`` (server default) or ``v3.0``; ``smart_uv`` requires ``v3.0``.
        """
        payload: Dict[str, Any] = {"input": input}
        if model is not None:
            payload["model"] = _LEGACY_LOWPOLY_MODEL_VERSIONS.get(model, model)
        for key, value in (("face_limit", face_limit), ("quad", quad), ("bake", bake), ("smart_uv", smart_uv)):
            if value is not None:
                payload[key] = value
        if part_names:
            payload["part_names"] = list(part_names)
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/mesh/decimate", payload)

    async def smart_lowpoly(
        self,
        original_model_task_id: str,
        model_version: Optional[str] = None,
        quad: Optional[bool] = False,
        part_names: Optional[List[str]] = None,
        face_limit: Optional[int] = None,
        bake: Optional[bool] = True,
        smart_uv: Optional[bool] = None,
        **kwargs: Any,
    ) -> str:
        """Convert a high-poly model to low-poly; see :meth:`mesh_decimate`."""
        extra = self._non_default("smart_lowpoly", {"quad": quad, "bake": bake})
        extra.update(kwargs)
        return await self.mesh_decimate(
            original_model_task_id,
            model=model_version,
            face_limit=face_limit,
            part_names=part_names,
            smart_uv=smart_uv,
            **extra,
        )

    async def mesh_uv(self, original_model_task_id: str, model_version: Optional[str] = None, **kwargs: Any) -> str:
        """
        Smart UV unwrap (``POST /v3/mesh/uv``).

        The finished task carries ``output.model_url`` and a UV atlas preview
        ``output.uv_render_url``. Extra keyword arguments (e.g. ``export_orientation``) are sent
        as-is.
        """
        payload: Dict[str, Any] = {"input": original_model_task_id}
        if model_version is not None:
            payload["model"] = model_version
        self._merge_extra(payload, kwargs)
        return await self._submit("/v3/mesh/uv", payload)
