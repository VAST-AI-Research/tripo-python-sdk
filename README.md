# Tripo3d Python SDK

The Tripo3d Python SDK is the official Python client library for the [Tripo 3D Generation API](https://tripo3d.ai/). With this SDK, you can easily generate high-quality 3D models.

> **1.0.0 uses Tripo apiv3.** The v2 API is shut down on 2026-10-31 and 0.x releases stop
> working then. 1.x keeps the 0.x method names and parameters, so upgrading is usually just
> `pip install -U "tripo3d>=1.0.0,<2.0.0"`. See [CHANGELOG.md](CHANGELOG.md) and
> [Migrating from 0.x](docs/API.md#migrating-from-0x).

## Features

- Text-to-3D model generation
- Image-to-3D model generation
- Multi-view to 3D model generation
- **Text-to-image and advanced image generation** (multi-model, multi-reference, templates)
- **Multiview image generation and editing**
- **One-shot model animation** (auto rig + retarget)
- **External model import** (GLB / OBJ / FBX / STL)
- Mesh editing including mesh segmentation, mesh completion, smart lowpoly and **Smart UV** (`mesh_uv`)
- Model conversion
- Rigging (v1.0 / v2.5 / v3.0), retarget and **text to motion**
- Image to depth and image to Gaussian splat
- Asynchronous API support
- Complete type hints

Refine and stylize are no longer supported: `refine_model` / `stylize_model` raise an error and send no request.

## Installation

```bash
pip install "tripo3d>=1.0.0,<2.0.0"
```

China mainland accounts use `TripoClient(IS_GLOBAL=False)` (`https://openapi.tripo3d.com`).

## Quick Start

### Initialization

```python
import asyncio
from tripo3d import TripoClient

async def main():
    # Initialize client with API key
    client = TripoClient(api_key="your_api_key")

    # Or read from environment variable
    # export TRIPO_API_KEY=your_api_key
    # client = TripoClient()

    # Use the client
    # ...

    # Close client connection
    await client.close()

# Run async function
asyncio.run(main())
```

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
                "path/to/left.jpg",    # Left view (optional, or None)
                "path/to/back.jpg",    # Back view (optional, or None)
                "path/to/right.jpg"    # Right view (optional, or None)
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

### Smart UV

```python
import asyncio
from tripo3d import TripoClient, TaskStatus

async def smart_uv(model_task_id):
    async with TripoClient() as client:
        task = await client.wait_for_task(await client.mesh_uv(model_task_id))
        if task.status == TaskStatus.SUCCESS:
            files = await client.download_task_models(task, "./output")
            print(files["model"], files.get("uv_render"))

asyncio.run(smart_uv("<task_id of a generated or imported model>"))
```

## Advanced Usage

For more advanced usage examples, check out the [examples](https://github.com/VAST-AI-Research/tripo-python-sdk/tree/master/examples) directory.

## API Reference

The complete API documentation can be found [here](https://github.com/VAST-AI-Research/tripo-python-sdk/blob/master/docs/API.md).

## License

MIT 