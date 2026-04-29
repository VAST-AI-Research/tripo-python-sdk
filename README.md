# Tripo3d Python SDK

The Tripo3d Python SDK is the official Python client library for the [Tripo 3D Generation API](https://tripo3d.ai/). With this SDK, you can easily generate high-quality 3D models.

## Features

- Text-to-3D model generation
- Image-to-3D model generation
- Multi-view to 3D model generation
- **Text-to-image and advanced image generation** (multi-model, multi-reference, templates)
- **Multiview image generation and editing**
- **One-shot model animation** (auto rig + retarget)
- **External model import** (GLB / OBJ / FBX / STL)
- Mesh editing including mesh segmentation, mesh completion and smart lowpoly
- Model conversion and stylization
- Rigging and retarget
- **China mainland region support** (`region="cn"`)
- Asynchronous API support
- Complete type hints

## Installation

```bash
pip install tripo3d
```

## Quick Start

### Initialization

```python
import asyncio
from tripo3d import TripoClient

async def main():
    # Overseas users (default)
    client = TripoClient(api_key="your_api_key")

    # China mainland users
    client = TripoClient(api_key="your_api_key", region="cn")

    # Or read API key from environment variable
    # export TRIPO_API_KEY=your_api_key
    # client = TripoClient()                     # overseas
    # client = TripoClient(region="cn")          # china mainland

    await client.close()

asyncio.run(main())
```

> **Region differences**: `region="ov"` uses `api.tripo3d.ai` and AWS S3 for uploads.
> `region="cn"` uses `api.tripo3d.com` and Baidu BOS. STS upload, bucket names, and
> available `generate_image` model versions are handled automatically.

### Text to 3D Model

```python
import asyncio
from tripo3d import TripoClient

async def text_to_model_example():
    async with TripoClient() as client:
        # Create text to 3D model task
        task_id = await client.text_to_model(
            prompt="A cute cat",
            negative_prompt="low quality, blurry",
        )

        print(f"Task ID: {task_id}")

        # Wait for task completion
        task = await client.wait_for_task(task_id)

        if task.status == TaskStatus.SUCCESS:
            print(f"Task completed successfully!")

            # Download model files
            downloaded_files = await client.download_task_models(task, "./output")

            # Print downloaded file paths
            for model_type, file_path in downloaded_files.items():
                if file_path:
                    print(f"Downloaded {model_type}: {file_path}")

asyncio.run(text_to_model_example())
```

### Image to 3D Model

```python
import asyncio
from tripo3d import TripoClient

async def image_to_model_example():
    async with TripoClient() as client:
        # Create image to 3D model task
        task_id = await client.image_to_model(
            image="path/to/your/image.jpg",
        )

        print(f"Task ID: {task_id}")

        # Wait for task completion and show progress
        task = await client.wait_for_task(task_id, verbose=True)

        if task.status == TaskStatus.SUCCESS:
            print(f"Task completed successfully!")

            # Download model files
            downloaded_files = await client.download_task_models(task, "./output")

            # Print downloaded file paths
            for model_type, file_path in downloaded_files.items():
                if file_path:
                    print(f"Downloaded {model_type}: {file_path}")

asyncio.run(image_to_model_example())
```

### Multi-view to 3D Model

```python
import asyncio
from tripo3d import TripoClient

async def multiview_to_model_example():
    async with TripoClient() as client:
        # Create multi-view to 3D model task
        task_id = await client.multiview_to_model(
            images=[
                "path/to/front.jpg",   # Front view (required)
                "path/to/back.jpg",    # Back view (optional)
                "path/to/left.jpg",    # Left view (optional)
                "path/to/right.jpg"    # Right view (optional)
            ],
        )

        print(f"Task ID: {task_id}")

        # Wait for task completion and show progress
        task = await client.wait_for_task(task_id, verbose=True)

        if task.status == TaskStatus.SUCCESS:
            print(f"Task completed successfully!")

            # Download model files
            downloaded_files = await client.download_task_models(task, "./output")

            # Print downloaded file paths
            for model_type, file_path in downloaded_files.items():
                if file_path:
                    print(f"Downloaded {model_type}: {file_path}")

asyncio.run(multiview_to_model_example())
```

### Check Account Balance

```python
import asyncio
from tripo3d import TripoClient

async def check_balance():
    async with TripoClient() as client:
        balance = await client.get_balance()
        print(f"Available balance: {balance.balance}")
        print(f"Frozen amount: {balance.frozen}")

asyncio.run(check_balance())
```

## Advanced Usage

For more advanced usage examples, check out the [examples](https://github.com/VAST-AI-Research/tripo-python-sdk/tree/master/examples) directory.

## API Reference

The complete API documentation can be found [here](https://github.com/VAST-AI-Research/tripo-python-sdk/blob/master/docs/API.md).

## License

MIT 