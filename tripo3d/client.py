"""
Tripo 3D Generation API Client.

This module provides a client for the Tripo 3D Generation API.
"""

import os
import asyncio
import warnings
from typing import Dict, List, Optional, Any, Union
import re

from .models import ModelStyle, Animation, PostStyle, Task, Balance, TaskStatus, RigType, RigSpec
from .client_impl import ClientImpl
from .exceptions import TripoRequestError

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

        self._impl = ClientImpl(self.api_key, self.BASE_URL)


    async def close(self) -> None:
        """Close any open connections."""
        await self._impl.close()

    def _is_ssl_error(self, error: Exception) -> bool:
        """Check if the error is an SSL certificate verification error."""
        error_str = str(error).lower()
        ssl_error_indicators = [
            'ssl certificate verification error',
            'certificate_verify_failed',
            'unable to get local issuer certificate',
            'ssl: certificate_verify_failed',
            'sslcertverificationerror'
        ]
        return any(indicator in error_str for indicator in ssl_error_indicators)

    async def _download_with_ssl_retry(self, url: str, output_path: str) -> None:
        """Download file with automatic SSL error retry."""
        try:
            # First try with normal SSL verification
            await self._impl.download_file(url, output_path)
        except Exception as e:
            if self._is_ssl_error(e):
                warnings.warn(
                    "SSL certificate verification failed during download. Automatically retrying with SSL verification disabled. "
                    "This reduces security but allows the download to proceed. "
                    "Consider updating your system's certificate store for better security.",
                    UserWarning
                )
                # Create a new implementation with SSL disabled just for this download
                from .client_impl import ClientImpl
                ssl_disabled_impl = ClientImpl(self.api_key, self.BASE_URL, verify_ssl=False)
                try:
                    await ssl_disabled_impl.download_file(url, output_path)
                finally:
                    await ssl_disabled_impl.close()
            else:
                raise

    async def __aenter__(self) -> 'TripoClient':
        """Enter the async context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the async context manager."""
        await self.close()

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
        # Add region header for China mainland users
        headers = {}
        from .geo_utils import get_china_mainland_status
        if get_china_mainland_status():
            headers["X-Tripo-Region"] = "rg2"

        response = await self._impl._request("GET", f"/task/{task_id}", headers=headers)
        return Task.from_dict(response["data"])


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
        response = await self._impl._request("POST", "/task", json_data=task_data)
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
        response = await self._impl._request("GET", "/user/balance")
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
                polling_interval = max(2, task.running_left_time * 0.5)
            else:
                polling_interval = polling_interval * 2
            # Wait before polling again
            await asyncio.sleep(polling_interval)


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
        result = {}

        def get_extension(url: str) -> str:
            # Remove query parameters
            path = url.split('?')[0]
            # Get the last path component
            filename = path.split('/')[-1]
            # Get the extension, or default to .glb if none
            ext = os.path.splitext(filename)[1]
            return ext if ext else '.glb'

        async def download_file(url: str, filename: str) -> Optional[str]:
            if not url:
                return None

            output_path = os.path.join(output_dir, filename)
            # Use the download method with SSL retry
            await self._download_with_ssl_retry(url, output_path)
            return output_path

        # Collect all files to download
        download_tasks = []

        # Main model
        if hasattr(task.output, 'model') and task.output.model:
            ext = get_extension(task.output.model)
            model_filename = f"{task.task_id}_model{ext}"
            download_tasks.append(('model', task.output.model, model_filename))

        # Base model
        if hasattr(task.output, 'base_model') and task.output.base_model:
            ext = get_extension(task.output.base_model)
            base_filename = f"{task.task_id}_base{ext}"
            download_tasks.append(('base_model', task.output.base_model, base_filename))

        # PBR model
        if hasattr(task.output, 'pbr_model') and task.output.pbr_model:
            ext = get_extension(task.output.pbr_model)
            pbr_filename = f"{task.task_id}_pbr{ext}"
            download_tasks.append(('pbr_model', task.output.pbr_model, pbr_filename))

        # Download all files concurrently
        if download_tasks:
            download_coroutines = [
                download_file(url, filename)
                for _, url, filename in download_tasks
            ]

            download_results = await asyncio.gather(*download_coroutines, return_exceptions=True)

            # Process download results
            for i, (model_type, url, filename) in enumerate(download_tasks):
                download_result = download_results[i]
                if isinstance(download_result, Exception):
                    result[model_type] = None
                else:
                    result[model_type] = download_result

        return result


    async def download_rendered_image(
        self,
        task: Task,
        output_dir: str,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """
        Download the rendered image from a completed task.

        Args:
            task: The completed task object.
            output_dir: Directory to save the downloaded file.
            filename: Optional custom filename. If not provided, will use task_id_rendered.jpg

        Returns:
            The path to the downloaded file, or None if no rendered image is available.

        Raises:
            TripoRequestError: If the download fails.
            ValueError: If the task is not successful or output_dir doesn't exist.
            FileNotFoundError: If output_dir doesn't exist.
        """
        if task.status != TaskStatus.SUCCESS:
            raise ValueError(f"Cannot download files from task with status: {task.status}")

        if not os.path.exists(output_dir):
            raise FileNotFoundError(f"Output directory not found: {output_dir}")

        # If there's no rendered image, return None
        if not task.output.rendered_image:
            return None

        # Determine the file extension from the URL
        def get_extension(url: str) -> str:
            # Remove query parameters
            path = url.split('?')[0]
            # Get the last path component
            filename = path.split('/')[-1]
            # Get the extension, or default to .jpg if none
            ext = os.path.splitext(filename)[1]
            return ext if ext else '.jpg'

        # Get the file extension
        ext = get_extension(task.output.rendered_image)

        # Use provided filename or default
        output_filename = filename if filename else f"{task.task_id}_rendered{ext}"
        output_path = os.path.join(output_dir, output_filename)

        # Download the file with SSL retry
        await self._download_with_ssl_retry(task.output.rendered_image, output_path)

        return output_path

    async def upload_file(self, file_path: str) -> str:
        """Upload a file to the API."""
        """
        Upload a file to the API.

        Args:
            file_path: Path to the file to upload.

        Returns:
            The file token for the uploaded file.

        Raises:
            TripoRequestError: If the upload fails.
            FileNotFoundError: If the file doesn't exist.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            import boto3
            response = await self._impl._request('POST', "/upload/sts/token", json_data={"format": "jpeg"})
            s3_client = boto3.client(
                's3',
                aws_access_key_id=response["data"]["sts_ak"],
                aws_secret_access_key=response["data"]["sts_sk"],
                aws_session_token=response["data"]["session_token"]
            )
            s3_client.upload_file(file_path, response["data"]["resource_bucket"], response["data"]["resource_uri"])
            return {
                "object": {
                    "bucket": response["data"]["resource_bucket"],
                    "key": response["data"]["resource_uri"]
                }
            }
        except ImportError:
            # If boto3 is not available, fall back to standard upload
            file_token = await self._impl.upload_file(file_path)
            return { "file_token": file_token }


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
            upload_result = await self.upload_file(image)
            file_content.update(upload_result)
        return file_content


    async def text_to_model(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        model_version: Optional[str] = "v2.5-20250123",
        face_limit: Optional[int] = None,
        texture: Optional[bool] = True,
        pbr: Optional[bool] = True,
        image_seed: Optional[int] = None,
        model_seed: Optional[int] = None,
        texture_seed: Optional[int] = None,
        texture_quality: str = "standard",
        style: Optional[ModelStyle] = None,
        auto_size: bool = False,
        quad: bool = False,
        compress: bool = False,
        generate_parts : bool = False,
        smart_low_poly: bool = False,
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
            image_seed: The image seed.
            model_seed: The model seed.
            texture_seed: The texture seed.
            texture_quality: The texture quality.
            style: Style to apply from ModelStyle enum.
            auto_size: Whether to automatically determine the model size.
            quad: Whether to generate a quad model.
            compress: Whether to compress the model.
            generate_parts: Whether to generate parts.
            smart_low_poly: Whether to use smart low poly.
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

        if image_seed is not None:
            task_data["image_seed"] = image_seed

        if model_seed is not None:
            task_data["model_seed"] = model_seed

        if texture_seed is not None:
            task_data["texture_seed"] = texture_seed

        if style:
            task_data["style"] = style

        if compress:
            task_data["compress"] = 'geometry'

        if generate_parts:
            task_data["generate_parts"] = generate_parts

        if smart_low_poly:
            task_data["smart_low_poly"] = smart_low_poly

        return await self.create_task(task_data)

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
        quad: bool = False,
        compress: bool = False,
        generate_parts : bool = False,
        smart_low_poly: bool = False,
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
            compress: Whether to compress the model.
            generate_parts: Whether to generate parts.
            smart_low_poly: Whether to use smart low poly.
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
            task_data["style"] = style

        if compress:
            task_data["compress"] = 'geometry'

        if generate_parts:
            task_data["generate_parts"] = generate_parts

        if smart_low_poly:
            task_data["smart_low_poly"] = smart_low_poly

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
        quad: bool = False,
        compress: bool = False,
        generate_parts : bool = False,
        smart_low_poly: bool = False,
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
            compress: Whether to compress the model.
            generate_parts: Whether to generate parts.
            smart_low_poly: Whether to use smart low poly.
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

        if compress:
            task_data["compress"] = 'geometry'

        if generate_parts:
            task_data["generate_parts"] = generate_parts

        if smart_low_poly:
            task_data["smart_low_poly"] = smart_low_poly

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
        pivot_to_center_bottom: bool = False,
        with_animation: bool = True,
        pack_uv: bool = False,
        bake: bool = True,
        part_names: Optional[List[str]] = None,
        export_vertex_colors: bool = False,
        animate_in_place: bool = False,
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
            with_animation: Whether to export animation. Default: False
            pack_uv: Whether to pack UV. Default: False
            bake: Whether to bake the model. Default: True
            part_names: List of part names to export.
            export_vertex_colors: Whether to export vertex colors.
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
            "pivot_to_center_bottom": pivot_to_center_bottom,
            "with_animation": with_animation,
            "pack_uv": pack_uv,
            "bake": bake,
            "export_vertex_colors": export_vertex_colors,
            "animate_in_place": animate_in_place
        }

        if part_names is not None:
            task_data["part_names"] = part_names

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
            "style": style,
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
        texture_alignment: str = "original_image",
        part_names: Optional[List[str]] = None,
        compress: bool = False,
        bake: bool = True,
        text_prompt: Optional[str] = None,
        image_prompt: Optional[str] = None,
        style_image: Optional[str] = None,
        model_version: Optional[str] = "v3.0-20250812",
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
            part_names: List of part names to texture.
            compress: Whether to compress the model.
            bake: Whether to bake the model.
            text_prompt: Text prompt for texture generation.
            image_prompt: Image prompt for texture generation. It Can be:
                  - A path to a local image file
                  - A URL to an image
                  - An image token from previous upload
            style_image: Style image for texture generation. The same format as image_prompt.
            model_version: The model version to use.
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
            "texture_alignment": texture_alignment,
            "bake": bake,
            "model_version": model_version
        }

        if model_seed is not None:
            task_data["model_seed"] = model_seed

        if texture_seed is not None:
            task_data["texture_seed"] = texture_seed

        if texture_quality is not None:
            task_data["texture_quality"] = texture_quality

        if part_names is not None:
            task_data["part_names"] = part_names

        if compress:
            task_data["compress"] = 'geometry'

        if text_prompt or image_prompt or style_image:
            task_data["texture_prompt"] = {}
            if text_prompt is not None:
                task_data["texture_prompt"]["text"] = text_prompt

            if image_prompt is not None:
                task_data["texture_prompt"]["image"] = await self._image_to_file_content(image_prompt)

            if style_image is not None:
                task_data["texture_prompt"]["style_image"] = await self._image_to_file_content(style_image)

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
        model_version: Optional[str] = "v2.0-20250506",
        out_format: str = "glb",
        rig_type: Optional[RigType] = RigType.BIPED,
        spec: Optional[RigSpec] = RigSpec.TRIPO,
    ) -> str:
        """
        Rig a 3D model for animation.

        Args:
            original_model_task_id: The task ID of the original model.
            out_format: Output format, either "glb" or "fbx". Default: "glb"
            rig_type: Rigging type, either "biped" or "quadruped" or "hexapod" or "octopod" or "avian" or "serpentine" or "aquatic" or "others". Default: "biped"
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

        task_data = {
            "type": "animate_rig",
            "original_model_task_id": original_model_task_id,
            "model_version": model_version,
            "out_format": out_format,
            "rig_type": rig_type,
            "spec": spec
        }

        return await self.create_task(task_data)

    async def retarget_animation(
        self,
        original_model_task_id: str,
        animation: Union[Animation, List[Animation]],
        out_format: str = "glb",
        bake_animation: bool = True,
        export_with_geometry: bool = False,
        animate_in_place: bool = False,
    ) -> str:
        """
        Apply an animation to a rigged model.

        Args:
            original_model_task_id: The task ID of the original model.
            animation: The animation to apply from Animation enum.
            out_format: Output format, either "glb" or "fbx". Default: "glb"
            bake_animation: Whether to bake the animation. Default: True
            export_with_geometry: Whether to export the animation with geometry. Default: False
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
            "out_format": out_format,
            "bake_animation": bake_animation,
            "export_with_geometry": export_with_geometry,
            "animate_in_place": animate_in_place
        }

        if isinstance(animation, list):
            task_data["animations"] = animation
        else:
            task_data["animation"] = animation

        return await self.create_task(task_data)

    async def mesh_segmentation(
        self,
        original_model_task_id: str,
        model_version: Optional[str] = "v1.0-20250506",
    ) -> str:
        """
        Segment a 3D model.

        Args:
            original_model_task_id: The task ID of the original model.
            model_version: The model version to use.
        Returns:
            The task ID.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        task_data = {
            "type": "mesh_segmentation",
            "original_model_task_id": original_model_task_id,
            "model_version": model_version
        }

        return await self.create_task(task_data)

    async def mesh_completion(
        self,
        original_model_task_id: str,
        model_version: Optional[str] = "v1.0-20250506",
        part_names: Optional[List[str]] = None,
    ) -> str:
        """
        Complete a 3D model.

        Args:
            original_model_task_id: The task ID of the original model.
            model_version: The model version to use.
            part_names: List of part names to complete.
        Returns:
            The task ID.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        task_data = {
            "type": "mesh_completion",
            "original_model_task_id": original_model_task_id,
            "model_version": model_version
        }

        if part_names is not None:
            task_data["part_names"] = part_names

        return await self.create_task(task_data)

    async def smart_lowpoly(
        self,
        original_model_task_id: str,
        model_version: Optional[str] = "P-v1.0-20250506",
        quad: bool = False,
        part_names: Optional[List[str]] = None,
        face_limit: Optional[int] = 4000,
        bake: bool = True,
    ) -> str:
        """
        Convert a high poly model to a low poly model.

        Args:
            original_model_task_id: The task ID of the original model.
            model_version: The model version to use.
            quad: Whether to generate a quad model.
            part_names: List of part names to complete.
            face_limit: The maximum number of faces.
            bake: Whether to bake the model.
        Returns:
            The task ID.

        Raises:
            TripoRequestError: If the request fails.
            TripoAPIError: If the API returns an error.
        """
        task_data = {
            "type": "highpoly_to_lowpoly",
            "original_model_task_id": original_model_task_id,
            "model_version": model_version,
            "quad": quad,
            "bake": bake,
            "face_limit": face_limit
        }

        if part_names is not None:
            task_data["part_names"] = part_names

        return await self.create_task(task_data)
