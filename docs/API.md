# Tripo API Reference

## TripoClient

The `TripoClient` class is the main entry point for interacting with the Tripo API.

```python
from tripo import TripoClient

# Initialize with API key
client = TripoClient(api_key="your_api_key")

# Or use environment variable
# export TRIPO_API_KEY=your_api_key
client = TripoClient()
```

### Context Manager

The `TripoClient` can be used as an async context manager to automatically close the connection when done:

```python
async with TripoClient() as client:
    # Use the client
    # ...
```

### Methods

#### text_to_model

```python
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
    style: Optional[str] = None,
    auto_size: bool = False,
    quad: bool = False
) -> str
```

Creates a 3D model from a text prompt.

**Parameters:**

- `prompt`: The text prompt for generating the 3D model.
- `negative_prompt`: Text prompt for characteristics to avoid.
- `model_version`: The version of the model to use.
- `face_limit`: Maximum number of faces for the generated model.
- `texture`: Whether to generate texture (default: True).
- `pbr`: Whether to generate PBR materials (default: True).
- `text_seed`: Seed for text-to-text step randomization.
- `model_seed`: Seed for 3D model generation randomization.
- `texture_seed`: Seed for texture generation randomization.
- `texture_quality`: Quality of the texture, "standard" or "detailed".
- `style`: Style to apply to the model.
- `auto_size`: Whether to automatically determine the model size.
- `quad`: Whether to generate a quad (4-sided) model.

**Returns:**
- The task ID as a string.

**Example:**

```python
task_id = await client.text_to_model(
    prompt="A small house with a red roof",
    negative_prompt="poorly made, damaged",
)
```

#### image_to_model

```python
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
    style: Optional[str] = None,
    auto_size: bool = False,
    orientation: str = "default",
    quad: bool = False
) -> str
```

Creates a 3D model from an image.

**Parameters:**

- `image`: The image input. Can be:
  - A path to a local image file
  - A URL to an image
  - An image token from previous upload
- `model_version`: The version of the model to use.
- `face_limit`: Maximum number of faces for the generated model.
- `texture`: Whether to generate texture (default: True).
- `pbr`: Whether to generate PBR materials (default: True).
- `model_seed`: Seed for 3D model generation randomization.
- `texture_seed`: Seed for texture generation randomization.
- `texture_quality`: Quality of the texture, "standard" or "detailed".
- `texture_alignment`: How to align the texture, "original_image" or "geometry".
- `style`: Style to apply to the model.
- `auto_size`: Whether to automatically determine the model size.
- `orientation`: The orientation of the model, "default" or "align_image".
- `quad`: Whether to generate a quad (4-sided) model.

**Returns:**
- The task ID as a string.

**Raises:**
- `TripoRequestError`: If the request fails.
- `TripoAPIError`: If the API returns an error.
- `FileNotFoundError`: If the image file does not exist.
- `ValueError`: If no image is provided.

**Example:**

```python
task_id = await client.image_to_model(
    image="path/to/car.jpg",
)

# Using a URL
task_id = await client.image_to_model(
    image="https://example.com/car.jpg",
)

# Using a previously uploaded image token
task_id = await client.image_to_model(
    image="12345678-1234-5678-1234-567812345678",
)
```

#### get_task

```python
async def get_task(self, task_id: str) -> Task
```

Get the status and details of a task.

**Parameters:**
- `task_id`: The ID of the task to get.

**Returns:**
- A `Task` object containing task details.

**Example:**

```python
task = await client.get_task("task-12345")
print(f"Task status: {task.status}")
```

#### wait_for_task

```python
async def wait_for_task(
    self, 
    task_id: str, 
    polling_interval: float = 2.0,
    timeout: Optional[float] = None
) -> Task
```

Wait for a task to complete, polling at regular intervals.

**Parameters:**
- `task_id`: The ID of the task to wait for.
- `polling_interval`: How often to check the task status in seconds.
- `timeout`: Maximum time to wait for the task to complete in seconds. If None, wait indefinitely.

**Returns:**
- A `Task` object containing the completed task details.

**Example:**

```python
task = await client.wait_for_task("task-12345", timeout=300)
if task.status == "success":
    print(f"Model URL: {task.output.model}")
```

#### get_balance

```python
async def get_balance(self) -> Balance
```

Get the user's account balance.

**Returns:**
- A `Balance` object with account details.

**Example:**

```python
balance = await client.get_balance()
print(f"Available balance: {balance.balance}")
print(f"Frozen amount: {balance.frozen}")
```

#### upload_file

```python
async def upload_file(self, file_path: str) -> str
```

Upload a file to the API.

**Parameters:**
- `file_path`: The path to the file to upload.

**Returns:**
- The file token as a string.

**Example:**

```python
file_token = await client.upload_file("path/to/image.jpg")
```

#### create_task

```python
async def create_task(self, task_data: Dict[str, Any]) -> str
```

Create a task with custom parameters.

**Parameters:**
- `task_data`: Dictionary containing the task data.

**Returns:**
- The task ID as a string.

**Example:**

```python
task_id = await client.create_task({
    "type": "text_to_model",
    "prompt": "A shiny red apple",
    "texture": True
})
```

#### multiview_to_model

```python
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
    style: Optional[str] = None,
    auto_size: bool = False,
    orientation: str = "default",
    quad: bool = False
) -> str
```

Creates a 3D model from multiple view images.

**Parameters:**
- `images`: List of images. Each image can be:
  - A path to a local image file
  - A URL to an image
  - An image token from previous upload
- `model_version`: The version of the model to use.
- `face_limit`: Maximum number of faces for the generated model.
- `texture`: Whether to generate texture.
- `pbr`: Whether to generate PBR materials.
- `model_seed`: Seed for 3D model generation randomization.
- `texture_seed`: Seed for texture generation randomization.
- `texture_quality`: Quality of the texture, "standard" or "detailed".
- `texture_alignment`: How to align the texture, "original_image" or "geometry".
- `style`: Style to apply to the model.
- `auto_size`: Whether to automatically determine the model size.
- `orientation`: The orientation of the model, "default" or "align_image".
- `quad`: Whether to generate a quad (4-sided) model.

**Returns:**
- The task ID as a string.

#### convert_model

```python
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
) -> str
```

Convert a 3D model to different format.

**Parameters:**
- `original_model_task_id`: The task ID of the original model.
- `format`: Output format. One of: "GLTF", "USDZ", "FBX", "OBJ", "STL", "3MF".
- `quad`: Whether to generate quad mesh. Default: False
- `force_symmetry`: Whether to force model symmetry. Default: False
- `face_limit`: Maximum number of faces. Default: 10000
- `flatten_bottom`: Whether to flatten the bottom of the model. Default: False
- `flatten_bottom_threshold`: Threshold for bottom flattening. Default: 0.01
- `texture_size`: Size of the texture. Default: 4096
- `texture_format`: Format of the texture. One of: "BMP", "DPX", "HDR", "JPEG", "OPEN_EXR", "PNG", "TARGA", "TIFF", "WEBP". Default: "JPEG"
- `pivot_to_center_bottom`: Whether to move pivot point to center bottom. Default: False

**Returns:**
- The task ID as a string.

#### stylize_model

```python
async def stylize_model(
    self,
    original_model_task_id: str,
    style: str,
    block_size: int = 80
) -> str
```

Apply a style to an existing 3D model.

**Parameters:**
- `original_model_task_id`: The task ID of the model to stylize.
- `style`: Style to apply. One of:
  - "lego"
  - "voxel"
  - "voronoi"
  - "minecraft"
- `block_size`: Size of the blocks for stylization. Default: 80

**Returns:**
- The task ID as a string.

#### texture_model

```python
async def texture_model(
    self,
    original_model_task_id: str,
    texture: bool = True,
    pbr: bool = True,
    model_seed: Optional[int] = None,
    texture_seed: Optional[int] = None,
    texture_quality: Optional[str] = "standard",
    texture_alignment: str = "original_image"
) -> str
```

Generate new texture for an existing 3D model.

**Parameters:**
- `original_model_task_id`: The task ID of the model to texture.
- `texture`: Whether to generate texture. Default: True
- `pbr`: Whether to generate PBR materials. Default: True
- `model_seed`: Seed for model generation randomization.
- `texture_seed`: Seed for texture generation randomization.
- `texture_quality`: Quality of the texture. One of: "standard" or "detailed".
- `texture_alignment`: How to align the texture. One of: "original_image" or "geometry". Default: "original_image"

**Returns:**
- The task ID as a string.

#### refine_model

```python
async def refine_model(
    self,
    draft_model_task_id: str
) -> str
```

Refine an existing 3D model.

**Parameters:**
- `draft_model_task_id`: The task ID of the model to refine.

**Returns:**
- The task ID as a string.

#### download_task_models

```python
async def download_task_models(
    self,
    task: Task,
    output_dir: str,
) -> Dict[str, str]
```

Download model files from a completed task.

**Parameters:**
- `task`: The completed task object.
- `output_dir`: Directory to save the downloaded files.

**Returns:**
- A dictionary containing the paths to the downloaded files:
  ```python
  {
      "model": "path/to/model.glb",      # Path to the main model file
      "base_model": "path/to/base.glb",  # Path to the base model file
      "pbr_model": "path/to/pbr.glb"     # Path to the PBR model file
  }
  ```

**Raises:**
- `TripoRequestError`: If the download fails.
- `ValueError`: If the task is not successful or output directory doesn't exist.
- `FileNotFoundError`: If the output directory doesn't exist.

**Example:**

```python
# Wait for task completion
task = await client.wait_for_task(task_id)

if task.status == TaskStatus.SUCCESS:
    # Download model files
    downloaded_files = await client.download_task_models(task, "./output")
    
    # Print downloaded file paths
    for model_type, file_path in downloaded_files.items():
        if file_path:
            print(f"Downloaded {model_type}: {file_path}")
```