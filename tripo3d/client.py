"""
Tripo 3D Generation API Client.

This module provides a client for the Tripo 3D Generation API.
"""

import os
import json
import asyncio
from typing import Dict, List, Optional, Any, Union, BinaryIO, Tuple, cast
from urllib.parse import urljoin
import re

import aiohttp

from .models import ModelStyle, Animation, PostStyle, Task, Balance, TaskStatus
from .exceptions import TripoAPIError, TripoRequestError


class TripoClient:
    """Client for the Tripo 3D Generation API."""

    # The base URL for the Tripo API as specified in the OpenAPI schema
    BASE_URL = "https://api.tripo3d.ai/v2/openapi"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Tripo API client.

        Args:
            api_key: The API key for authentication. If not provided, it will be read from the
                     TRIPO_API_KEY environment variable.

        Raises:
            ValueError: If no API key is provided and the TRIPO_API_KEY environment variable is not set.
        """
        self.api_key = api_key or os.environ.get("TRIPO_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key is required. Provide it as an argument or set the TRIPO_API_KEY environment variable."
            )

        if not self.api_key.startswith('tsk_'):
            raise ValueError("API key must start with 'tsk_'")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure that an aiohttp session exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> 'TripoClient':
        """Enter the async context manager."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the async context manager."""
        await self.close()

    def _url(self, path: str) -> str:
        """
        Construct a full URL from a path.

        Args:
            path: The path to append to the base URL.

        Returns:
            The full URL.
        """
        # Remove leading slash if present
        path = path.lstrip('/')

        # Construct the full URL
        return f"{self.BASE_URL}/{path}"

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the API.

        Args:
            method: The HTTP method to use.
            path: The path to request.
            params: Query parameters.
            json_data: JSON data to send in the request body.
            data: Form data to send in the request body.
            headers: Additional headers to send with the request.

        Returns:
            The parsed JSON response.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
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

    async def get_task(self, task_id: str) -> Task:
        """
        Get the status of a task.

        Args:
            task_id: The ID of the task to get.

        Returns:
            The task data.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        response = await self._request("GET", f"/task/{task_id}")
        return Task.from_dict(response["data"])

    async def upload_file(self, file_path: str) -> str:
        """
        Upload a file to the API.

        Args:
            file_path: The path to the file to upload.

        Returns:
            The image token for the uploaded file.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
            FileNotFoundError: If the file does not exist.
        """
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

    async def create_task(self, task_data: Dict[str, Any]) -> str:
        """
        Create a task.

        Args:
            task_data: The task data.

        Returns:
            The task ID.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        response = await self._request("POST", "/task", json_data=task_data)
        return response["data"]["task_id"]

    async def get_balance(self) -> Balance:
        """
        Get the user's balance.

        Returns:
            The user's balance.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        response = await self._request("GET", "/balance")
        return Balance.from_dict(response["data"])

    async def wait_for_task(
        self,
        task_id: str,
        polling_interval: float = 2.0,
        timeout: Optional[float] = None,
        verbose: bool = False
    ) -> Task:
        """
        Wait for a task to complete.

        Args:
            task_id: The ID of the task to wait for.
            polling_interval: The interval in seconds to poll the task status.
            timeout: The maximum time in seconds to wait for the task to complete.
                    If None, wait indefinitely.

        Returns:
            The task data.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
            asyncio.TimeoutError: If the task does not complete within the timeout.
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check if we've exceeded the timeout
            if timeout is not None:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    raise asyncio.TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")

            # Get the task status
            task = await self.get_task(task_id)

            # If the task is done, return it
            if task.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.BANNED, TaskStatus.EXPIRED):
                if verbose:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    print(f"Task {task_id} {task.status} in {elapsed} seconds")
                return task

            if verbose:
                progress_bar = f"[{'=' * (task.progress // 5)}{' ' * (20 - task.progress // 5)}] {task.progress}%"
                remaining_time = f", estimated time remaining: {task.running_left_time}s" if hasattr(task, 'running_left_time') and task.running_left_time is not None else ""
                print(f"Task {task_id} is {task.status}. Progress: {progress_bar}{remaining_time}")

            # Calculate next polling interval based on estimated time remaining
            if hasattr(task, 'running_left_time') and task.running_left_time is not None:
                # Use 80% of the estimated remaining time as the next polling interval
                polling_interval = max(2, task.running_left_time * 0.8)
            else:
                polling_interval = polling_interval * 2
            # Wait before polling again
            await asyncio.sleep(polling_interval)

    async def text_to_model(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        model_version: Optional[str] = "v2.5-20250123",
        face_limit: Optional[int] = None,
        texture: Optional[bool] = True,
        pbr: Optional[bool] = True,
        text_seed: Optional[int] = None,
        model_seed: Optional[int] = None,
        texture_seed: Optional[int] = None,
        texture_quality: str = "standard",
        style: Optional[ModelStyle] = None,
        auto_size: bool = False,
        quad: bool = False
    ) -> str:
        """
        Create a text to 3D model task.

        Args:
            prompt: The text prompt.
            negative_prompt: The negative text prompt.
            model_version: The model version to use.
            face_limit: The maximum number of faces.
            texture: Whether to generate texture.
            pbr: Whether to generate PBR materials.
            text_seed: The text seed.
            model_seed: The model seed.
            texture_seed: The texture seed.
            texture_quality: The texture quality.
            style: Style to apply from ModelStyle enum.
            auto_size: Whether to automatically determine the model size.
            quad: Whether to generate a quad model.

        Returns:
            The task ID.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
            ValueError: If the prompt is empty.
        """
        if not prompt:
            raise ValueError("Prompt is required.")

        task_data = {
            "type": "text_to_model",
            "prompt": prompt,
            "model_version": model_version,
            "texture": texture,
            "pbr": pbr,
            "auto_size": auto_size,
            "quad": quad,
            "texture_quality": texture_quality
        }

        if negative_prompt:
            task_data["negative_prompt"] = negative_prompt

        if face_limit is not None:
            task_data["face_limit"] = face_limit

        if text_seed is not None:
            task_data["text_seed"] = text_seed

        if model_seed is not None:
            task_data["model_seed"] = model_seed

        if texture_seed is not None:
            task_data["texture_seed"] = texture_seed

        if style:
            task_data["style"] = style.value

        return await self.create_task(task_data)

    async def _image_to_file_content(self, image: str) -> Dict[str, Any]:
        file_content = {
            "type": "jpg"
        }
        # If image starts with http:// or https://, treat it as a URL
        if image.startswith(("http://", "https://")):
            file_content["url"] = image
        # If image looks like a token (no file extension and not a path)
        elif not os.path.exists(image) and re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', image, re.IGNORECASE):
            file_content["file_token"] = image
        else:
            # Treat as a local file path
            if not os.path.exists(image):
                raise FileNotFoundError(f"Image file not found: {image}")
            file_content["file_token"] = await self.upload_file(image)
        return file_content

    async def image_to_model(
        self,
        image: Optional[str] = None,
        model_version: Optional[str] = "v2.5-20250123",
        face_limit: Optional[int] = None,
        texture: Optional[bool] = True,
        pbr: Optional[bool] = True,
        model_seed: Optional[int] = None,
        texture_seed: Optional[int] = None,
        texture_quality: str = "standard",
        texture_alignment: str = "original_image",
        style: Optional[ModelStyle] = None,
        auto_size: bool = False,
        orientation: str = "default",
        quad: bool = False
    ) -> str:
        """
        Create an image to 3D model task.

        Args:
            image: The image input. Can be:
                  - A path to a local image file
                  - A URL to an image
                  - An image token from previous upload
            model_version: The model version to use.
            face_limit: The maximum number of faces.
            texture: Whether to generate texture.
            pbr: Whether to generate PBR materials.
            model_seed: The model seed.
            texture_seed: The texture seed.
            texture_quality: The texture quality.
            texture_alignment: The texture alignment.
            style: Style to apply from ModelStyle enum.
            auto_size: Whether to automatically determine the model size.
            orientation: The orientation.
            quad: Whether to generate a quad model.

        Returns:
            The task ID.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
            FileNotFoundError: If the image file does not exist.
            ValueError: If no image is provided.
        """
        # Check if image is a token, local path, or URL
        if image is None:
            raise ValueError("Image is required")

        # Create the task
        task_data = {
            "type": "image_to_model",
            "file": await self._image_to_file_content(image),
            "model_version": model_version,
            "texture": texture,
            "pbr": pbr,
            "auto_size": auto_size,
            "quad": quad,
            "texture_quality": texture_quality,
            "texture_alignment": texture_alignment,
            "orientation": orientation
        }

        if face_limit is not None:
            task_data["face_limit"] = face_limit

        if model_seed is not None:
            task_data["model_seed"] = model_seed

        if texture_seed is not None:
            task_data["texture_seed"] = texture_seed

        if style:
            task_data["style"] = style.value

        return await self.create_task(task_data)

    async def multiview_to_model(
        self,
        images: List[str],
        model_version: Optional[str] = "v2.5-20250123",
        face_limit: Optional[int] = None,
        texture: Optional[bool] = True,
        pbr: Optional[bool] = True,
        model_seed: Optional[int] = None,
        texture_seed: Optional[int] = None,
        texture_quality: str = "standard",
        texture_alignment: str = "original_image",
        auto_size: bool = False,
        orientation: str = "default",
        quad: bool = False
    ) -> str:
        """
        Create a 3D model from multiple view images.

        Args:
            images: List of images. Each image can be:
                   - A path to a local image file
                   - A URL to an image
                   - An image token from previous upload
            model_version: The model version to use.
            face_limit: Maximum number of faces for the generated model.
            texture: Whether to generate texture.
            pbr: Whether to generate PBR materials.
            model_seed: Seed for 3D model generation randomization.
            texture_seed: Seed for texture generation randomization.
            texture_quality: Quality of the texture.
            texture_alignment: How to align the texture.
            auto_size: Whether to automatically determine the model size.
            orientation: The orientation of the model.
            quad: Whether to generate a quad model.

        Returns:
            The task ID.
        """
        # Create tasks while preserving order
        tasks = []
        for i, image in enumerate(images):
            if image is not None:
                # Store both the task and its original index
                tasks.append((i, self._image_to_file_content(image)))
            else:
                tasks.append((i, None))

        # Initialize file_tokens list with the correct size
        file_tokens = [{} for _ in range(len(images))]

        # Wait for all uploads to complete and place results in correct positions
        for i, task in tasks:
            if task is not None:
                file_tokens[i] = await task

        # Create the task
        task_data = {
            "type": "multiview_to_model",
            "files": file_tokens,
            "model_version": model_version,
            "texture": texture,
            "pbr": pbr,
            "auto_size": auto_size,
            "quad": quad,
            "texture_quality": texture_quality,
            "texture_alignment": texture_alignment,
            "orientation": orientation
        }

        if face_limit is not None:
            task_data["face_limit"] = face_limit

        if model_seed is not None:
            task_data["model_seed"] = model_seed

        if texture_seed is not None:
            task_data["texture_seed"] = texture_seed

        if quad:
            task_data["quad"] = quad

        return await self.create_task(task_data)

    async def convert_model(
        self,
        original_model_task_id: str,
        format: str,
        quad: bool = False,
        force_symmetry: bool = False,
        face_limit: int = 10000,
        flatten_bottom: bool = False,
        flatten_bottom_threshold: float = 0.01,
        texture_size: int = 4096,
        texture_format: str = "JPEG",
        pivot_to_center_bottom: bool = False
    ) -> str:
        """
        Convert a 3D model to different format.

        Args:
            original_model_task_id: The task ID of the original model.
            format: Output format. One of: "GLTF", "USDZ", "FBX", "OBJ", "STL", "3MF"
            quad: Whether to generate quad mesh. Default: False
            force_symmetry: Whether to force model symmetry. Default: False
            face_limit: Maximum number of faces. Default: 10000
            flatten_bottom: Whether to flatten the bottom of the model. Default: False
            flatten_bottom_threshold: Threshold for bottom flattening. Default: 0.01
            texture_size: Size of the texture. Default: 4096
            texture_format: Format of the texture. One of: "BMP", "DPX", "HDR", "JPEG", "OPEN_EXR",
                          "PNG", "TARGA", "TIFF", "WEBP". Default: "JPEG"
            pivot_to_center_bottom: Whether to move pivot point to center bottom. Default: False

        Returns:
            The task ID.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        task_data = {
            "type": "convert_model",
            "original_model_task_id": original_model_task_id,
            "format": format,
            "quad": quad,
            "force_symmetry": force_symmetry,
            "face_limit": face_limit,
            "flatten_bottom": flatten_bottom,
            "flatten_bottom_threshold": flatten_bottom_threshold,
            "texture_size": texture_size,
            "texture_format": texture_format,
            "pivot_to_center_bottom": pivot_to_center_bottom
        }

        return await self.create_task(task_data)

    async def stylize_model(
        self,
        original_model_task_id: str,
        style: PostStyle,
        block_size: int = 80
    ) -> str:
        """
        Apply a style to an existing 3D model.

        Args:
            original_model_task_id: The task ID of the original model.
            style: Style to apply from PostStyle enum.
            block_size: Size of the blocks for stylization. Default: 80

        Returns:
            The task ID.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        task_data = {
            "type": "stylize_model",
            "original_model_task_id": original_model_task_id,
            "style": style.value,
            "block_size": block_size
        }

        return await self.create_task(task_data)

    async def texture_model(
        self,
        original_model_task_id: str,
        texture: bool = True,
        pbr: bool = True,
        model_seed: Optional[int] = None,
        texture_seed: Optional[int] = None,
        texture_quality: Optional[str] = "standard",
        texture_alignment: str = "original_image"
    ) -> str:
        """
        Generate new texture for an existing 3D model.

        Args:
            original_model_task_id: The task ID of the original model.
            texture: Whether to generate texture. Default: True
            pbr: Whether to generate PBR materials. Default: True
            model_seed: Seed for model generation randomization.
            texture_seed: Seed for texture generation randomization.
            texture_quality: Quality of the texture. One of:
                          - "standard"
                          - "detailed"
            texture_alignment: How to align the texture. One of:
                            - "original_image"
                            - "geometry"
                            Default: "original_image"

        Returns:
            The task ID.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        task_data = {
            "type": "texture_model",
            "original_model_task_id": original_model_task_id,
            "texture": texture,
            "pbr": pbr,
            "texture_alignment": texture_alignment
        }

        if model_seed is not None:
            task_data["model_seed"] = model_seed

        if texture_seed is not None:
            task_data["texture_seed"] = texture_seed

        if texture_quality is not None:
            task_data["texture_quality"] = texture_quality

        return await self.create_task(task_data)

    async def refine_model(
        self,
        draft_model_task_id: str
    ) -> str:
        """
        Refine an existing 3D model.

        Args:
            draft_model_task_id: The task ID of the draft model to refine.

        Returns:
            The task ID.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        task_data = {
            "type": "refine_model",
            "draft_model_task_id": draft_model_task_id
        }

        return await self.create_task(task_data)

    async def download_task_models(
        self,
        task: Task,
        output_dir: str,
    ) -> Dict[str, str]:
        """
        Download model files from a completed task.

        Args:
            task: The completed task object.
            output_dir: Directory to save the downloaded files.

        Returns:
            A dictionary containing the paths to the downloaded files:
            {
                "model": "path/to/model.glb",
                "base_model": "path/to/base_model.glb",
                "pbr_model": "path/to/pbr_model.glb"
            }

        Raises:
            TripoRequestError: If the download fails.
            ValueError: If the task is not successful or output_dir doesn't exist.
            FileNotFoundError: If output_dir doesn't exist.
        """
        if task.status != TaskStatus.SUCCESS:
            raise ValueError(f"Cannot download files from task with status: {task.status}")

        if not os.path.exists(output_dir):
            raise FileNotFoundError(f"Output directory not found: {output_dir}")

        session = await self._ensure_session()
        result = {}

        def get_extension(url: str) -> str:
            # 移除查询参数
            path = url.split('?')[0]
            # 获取最后一个路径组件
            filename = path.split('/')[-1]
            # 获取扩展名，如果没有则返回 .glb 作为默认值
            ext = os.path.splitext(filename)[1]
            return ext if ext else '.glb'

        async def download_file(url: str, filename: str) -> str:
            if not url:
                return None

            output_path = os.path.join(output_dir, filename)
            try:
                async with session.get(url) as response:
                    if response.status >= 400:
                        raise TripoRequestError(
                            status_code=response.status,
                            message=f"Failed to download {filename}: {response.reason}"
                        )
                    
                    with open(output_path, 'wb') as f:
                        while True:
                            chunk = await response.content.read(8192)  # 8KB chunks
                            if not chunk:
                                break
                            f.write(chunk)
                
                return output_path
            except aiohttp.ClientError as e:
                raise TripoRequestError(
                    status_code=0,
                    message=f"Download error for {filename}: {str(e)}"
                )

        # Download main model
        if task.output.model:
            ext = get_extension(task.output.model)
            model_filename = f"{task.task_id}_model{ext}"
            result["model"] = await download_file(task.output.model, model_filename)

        # Download base model
        if task.output.base_model:
            ext = get_extension(task.output.base_model)
            base_filename = f"{task.task_id}_base{ext}"
            result["base_model"] = await download_file(task.output.base_model, base_filename)

        # Download PBR model
        if task.output.pbr_model:
            ext = get_extension(task.output.pbr_model)
            pbr_filename = f"{task.task_id}_pbr{ext}"
            result["pbr_model"] = await download_file(task.output.pbr_model, pbr_filename)

        return result

    async def check_riggable(
        self,
        original_model_task_id: str
    ) -> str:
        """
        Check if a model can be rigged.

        Args:
            original_model_task_id: The task ID of the original model.

        Returns:
            The task ID for the rigging check task.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        task_data = {
            "type": "animate_prerigcheck",
            "original_model_task_id": original_model_task_id
        }

        return await self.create_task(task_data)

    async def rig_model(
        self,
        original_model_task_id: str,
        out_format: str = "glb",
        spec: str = "tripo"
    ) -> str:
        """
        Rig a 3D model for animation.

        Args:
            original_model_task_id: The task ID of the original model.
            out_format: Output format, either "glb" or "fbx". Default: "glb"
            spec: Rigging specification, either "mixamo" or "tripo". Default: "tripo"

        Returns:
            The task ID for the rigging task.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
            ValueError: If parameters are invalid.
        """
        if out_format not in ["glb", "fbx"]:
            raise ValueError("out_format must be either 'glb' or 'fbx'")
        
        if spec not in ["mixamo", "tripo"]:
            raise ValueError("spec must be either 'mixamo' or 'tripo'")

        task_data = {
            "type": "animate_rig",
            "original_model_task_id": original_model_task_id,
            "out_format": out_format,
            "spec": spec
        }

        return await self.create_task(task_data)

    async def retarget_animation(
        self,
        original_model_task_id: str,
        animation: Animation,
        out_format: str = "glb",
        bake_animation: bool = True
    ) -> str:
        """
        Apply an animation to a rigged model.

        Args:
            original_model_task_id: The task ID of the original model.
            animation: The animation to apply from Animation enum.
            out_format: Output format, either "glb" or "fbx". Default: "glb"
            bake_animation: Whether to bake the animation. Default: True

        Returns:
            The task ID for the animation retargeting task.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
            ValueError: If parameters are invalid.
        """
        if out_format not in ["glb", "fbx"]:
            raise ValueError("out_format must be either 'glb' or 'fbx'")

        task_data = {
            "type": "animate_retarget",
            "original_model_task_id": original_model_task_id,
            "animation": animation.value,
            "out_format": out_format,
            "bake_animation": bake_animation
        }

        return await self.create_task(task_data)

