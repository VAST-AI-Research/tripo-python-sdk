# Tripo API Reference

## TripoClient

The `TripoClient` class is the main entry point for interacting with the Tripo API.

```python
from tripo3d import TripoClient

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

#### Common Methods

##### upload_file

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

##### create_task

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

##### get_task

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

##### wait_for_task

```python
async def wait_for_task(
    self,
    task_id: str,
    polling_interval: float = 2.0,
    timeout: Optional[float] = None,
    verbose: bool = False
) -> Task
```

Wait for a task to complete, polling at regular intervals.

**Parameters:**
- `task_id`: The ID of the task to wait for.
- `polling_interval`: How often to check the task status in seconds.
- `timeout`: Maximum time to wait for the task to complete in seconds. If None, wait indefinitely.
- `verbose`: Whether to print progress information.

**Returns:**
- A `Task` object containing the completed task details.

**Example:**

```python
task = await client.wait_for_task("task-12345", timeout=300, verbose=True)
if task.status == "success":
    print(f"Model URL: {task.output.model}")
```

##### download_task_models

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

##### download_rendered_image

```python
async def download_rendered_image(
    self,
    task: Task,
    output_dir: str,
    filename: Optional[str] = None,
) -> Optional[str]
```

Download the rendered image from a completed task.

**Parameters:**
- `task`: The completed task object.
- `output_dir`: Directory to save the downloaded image.
- `filename`: Optional custom filename for the image.

**Returns:**
- The path to the downloaded image file, or None if no image is available.

**Example:**

```python
task = await client.wait_for_task(task_id)
if task.status == TaskStatus.SUCCESS:
    image_path = await client.download_rendered_image(task, "./output")
    if image_path:
        print(f"Downloaded rendered image: {image_path}")
```

##### get_balance

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

#### Generation Methods

##### text_to_model

```python
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
    generate_parts: bool = False,
    smart_low_poly: bool = False,
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
- `image_seed`: Seed for text-to-text step randomization.
- `model_seed`: Seed for 3D model generation randomization.
- `texture_seed`: Seed for texture generation randomization.
- `texture_quality`: Quality of the texture, "standard" or "detailed".
- `style`: Style to apply to the model from ModelStyle enum. Used for initial model generation.
- `auto_size`: Whether to automatically determine the model size.
- `quad`: Whether to generate a quad (4-sided) model.
- `compress`: Whether to compress the model geometry.
- `generate_parts`: Whether to generate model parts.
- `smart_low_poly`: Whether to use smart low poly generation.

**Returns:**
- The task ID as a string.

**Example:**

```python
task_id = await client.text_to_model(
    prompt="A small house with a red roof",
    negative_prompt="poorly made, damaged",
    compress=True,
    generate_parts=True
)
```

##### image_to_model

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
    style: Optional[ModelStyle] = None,
    auto_size: bool = False,
    orientation: str = "default",
    quad: bool = False,
    compress: bool = False,
    generate_parts: bool = False,
    smart_low_poly: bool = False,
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
- `style`: Style to apply to the model from ModelStyle enum. Used for initial model generation.
- `auto_size`: Whether to automatically determine the model size.
- `orientation`: The orientation of the model, "default" or "align_image".
- `quad`: Whether to generate a quad (4-sided) model.
- `compress`: Whether to compress the model geometry.
- `generate_parts`: Whether to generate model parts.
- `smart_low_poly`: Whether to use smart low poly generation.

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
    compress=True,
    generate_parts=True
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

##### multiview_to_model

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
    auto_size: bool = False,
    orientation: str = "default",
    quad: bool = False,
    compress: bool = False,
    generate_parts: bool = False,
    smart_low_poly: bool = False,
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
- `auto_size`: Whether to automatically determine the model size.
- `orientation`: The orientation of the model, "default" or "align_image".
- `quad`: Whether to generate a quad (4-sided) model.
- `compress`: Whether to compress the model geometry.
- `generate_parts`: Whether to generate model parts.
- `smart_low_poly`: Whether to use smart low poly generation.

**Returns:**
- The task ID as a string.

##### convert_model

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
    pivot_to_center_bottom: bool = False,
    with_animation: bool = False,
    pack_uv: bool = False,
    bake: bool = True,
    part_names: Optional[List[str]] = None,
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
- `with_animation`: Whether to export animation. Default: False
- `pack_uv`: Whether to pack UV. Default: False
- `bake`: Whether to bake the model. Default: True
- `part_names`: List of part names to export.

**Returns:**
- The task ID as a string.

##### stylize_model

```python
async def stylize_model(
    self,
    original_model_task_id: str,
    style: PostStyle,
    block_size: int = 80
) -> str
```

Apply a post-processing style to an existing 3D model.

**Parameters:**
- `original_model_task_id`: The task ID of the model to stylize.
- `style`: Style to apply from PostStyle enum. Available options:
  - `PostStyle.LEGO`
  - `PostStyle.VOXEL`
  - `PostStyle.VORONOI`
  - `PostStyle.MINECRAFT`
- `block_size`: Size of the blocks for stylization. Default: 80

**Returns:**
- The task ID as a string.

##### texture_model

```python
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
- `part_names`: List of part names to texture.
- `compress`: Whether to compress the model geometry.
- `bake`: Whether to bake the model. Default: True
- `text_prompt`: Text prompt for texture generation.
- `image_prompt`: Image prompt for texture generation. Can be:
  - A path to a local image file
  - A URL to an image
  - An image token from previous upload
- `style_image`: Style image for texture generation. Same format as image_prompt.

**Returns:**
- The task ID as a string.

##### refine_model

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

##### check_riggable

```python
async def check_riggable(
    self,
    original_model_task_id: str
) -> str
```

Check if a model can be rigged for animation.

**Parameters:**
- `original_model_task_id`: The task ID of the model to check.

**Returns:**
- The task ID for the rigging check task.

**Example:**

```python
# Check if model can be rigged
check_task_id = await client.check_riggable("task-12345")
check_result = await client.wait_for_task(check_task_id)

# Check the result
if check_result.output.riggable:
    print("Model can be rigged")
else:
    print("Model cannot be rigged")
```

##### rig_model

```python
async def rig_model(
    self,
    original_model_task_id: str,
    out_format: str = "glb",
    rig_type: Optional[RigType] = None,
    spec: Optional[RigSpec] = None,
) -> str
```

Rig a 3D model for animation.

**Parameters:**
- `original_model_task_id`: The task ID of the model to rig.
- `out_format`: Output format, either "glb" or "fbx". Default: "glb"
- `rig_type`: Rigging type from RigType enum. Available options:
  - `RigType.BIPED`
  - `RigType.QUADRUPED`
  - `RigType.HEXAPOD`
  - `RigType.OCTOPOD`
  - `RigType.AVIAN`
  - `RigType.SERPENTINE`
  - `RigType.AQUATIC`
  - `RigType.OTHERS`
- `spec`: Rigging specification from RigSpec enum. Available options:
  - `RigSpec.MIXAMO`
  - `RigSpec.TRIPO`

**Returns:**
- The task ID for the rigging task.

**Raises:**
- `ValueError`: If out_format is not "glb" or "fbx"
- `TripoRequestError`: If the request fails.
- `TripoAPIError`: If the API returns an error.

**Example:**

```python
# First check if model can be rigged
check_task_id = await client.check_riggable("task-12345")
check_result = await client.wait_for_task(check_task_id)

if check_result.output.riggable:
    # Rig the model
    rig_task_id = await client.rig_model(
        original_model_task_id="task-12345",
        out_format="glb",
        rig_type=RigType.BIPED,
        spec=RigSpec.TRIPO
    )
    rig_result = await client.wait_for_task(rig_task_id)
```

##### retarget_animation

```python
async def retarget_animation(
    self,
    original_model_task_id: str,
    animation: Union[Animation, List[Animation]],
    out_format: str = "glb",
    bake_animation: bool = True,
    export_with_geometry: bool = False,
) -> str
```

Apply an animation to a rigged model.

**Parameters:**
- `original_model_task_id`: The task ID of the original model.
- `animation`: The animation to apply from Animation enum, or a list of animations.
- `out_format`: Output format, either "glb" or "fbx". Default: "glb"
- `bake_animation`: Whether to bake the animation. Default: True
- `export_with_geometry`: Whether to export the animation with geometry. Default: False

**Returns:**
- The task ID as a string.

**Example:**

```python
# Apply single animation
task_id = await client.retarget_animation(
    original_model_task_id="task-12345",
    animation=Animation.WALK,
    out_format="glb"
)

# Apply multiple animations
task_id = await client.retarget_animation(
    original_model_task_id="task-12345",
    animation=[Animation.WALK, Animation.RUN],
    out_format="glb"
)
```

##### mesh_segmentation

```python
async def mesh_segmentation(
    self,
    original_model_task_id: str,
    model_version: Optional[str] = "v1.0-20250506",
) -> str
```

Segment a 3D model into parts.

**Parameters:**
- `original_model_task_id`: The task ID of the original model.
- `model_version`: The model version to use.

**Returns:**
- The task ID as a string.

##### mesh_completion

```python
async def mesh_completion(
    self,
    original_model_task_id: str,
    model_version: Optional[str] = "v1.0-20250506",
    part_names: Optional[List[str]] = None,
) -> str
```

Complete a 3D model or specific parts.

**Parameters:**
- `original_model_task_id`: The task ID of the original model.
- `model_version`: The model version to use.
- `part_names`: List of part names to complete.

**Returns:**
- The task ID as a string.

##### smart_lowpoly

```python
async def smart_lowpoly(
    self,
    original_model_task_id: str,
    model_version: Optional[str] = "P-v1.0-20250506",
    quad: bool = False,
    part_names: Optional[List[str]] = None,
    face_limit: Optional[int] = 4000,
    bake: bool = True,
) -> str
```

Convert a high poly model to a low poly model.

**Parameters:**
- `original_model_task_id`: The task ID of the original model.
- `model_version`: The model version to use.
- `quad`: Whether to generate a quad model.
- `part_names`: List of part names to process.
- `face_limit`: The maximum number of faces. Default: 4000
- `bake`: Whether to bake the model. Default: True

**Returns:**
- The task ID as a string.

## Enums

### Animation

Available preset animations for retargeting.

```python
class Animation(str, Enum):
    IDLE = "preset:idle"
    WALK = "preset:walk"
    RUN = "preset:run"
    DIVE = "preset:dive"
    CLIMB = "preset:climb"
    JUMP = "preset:jump"
    SLASH = "preset:slash"
    SHOOT = "preset:shoot"
    HURT = "preset:hurt"
    FALL = "preset:fall"
    TURN = "preset:turn"
    QUADRUPED_WALK = "preset:quadruped:walk"
    HEXAPOD_WALK = "preset:hexapod:walk"
    OCTOPOD_WALK = "preset:octopod:walk"
    SERPENTINE_MARCH = "preset:serpentine:march"
    AQUATIC_MARCH = "preset:aquatic:march"
```

### ModelStyle

Available styles for model generation.

```python
class ModelStyle(str, Enum):
    # Person styles
    PERSON_TO_CARTOON = "person:person2cartoon"

    # Animal styles
    ANIMAL_VENOM = "animal:venom"

    # Object styles
    OBJECT_CLAY = "object:clay"
    OBJECT_STEAMPUNK = "object:steampunk"
    OBJECT_CHRISTMAS = "object:christmas"
    OBJECT_BARBIE = "object:barbie"

    # Material styles
    GOLD = "gold"
    ANCIENT_BRONZE = "ancient_bronze"
```

### PostStyle

Available styles for model postprocessing.

```python
class PostStyle(str, Enum):
    # Stylization styles
    LEGO = "lego"
    VOXEL = "voxel"
    VORONOI = "voronoi"
    MINECRAFT = "minecraft"
```

### RigType

Available rigging types for models.

```python
class RigType(str, Enum):
    BIPED = "biped"
    QUADRUPED = "quadruped"
    HEXAPOD = "hexapod"
    OCTOPOD = "octopod"
    AVIAN = "avian"
    SERPENTINE = "serpentine"
    AQUATIC = "aquatic"
    OTHERS = "others"
```

### RigSpec

Available rigging specifications.

```python
class RigSpec(str, Enum):
    MIXAMO = "mixamo"
    TRIPO = "tripo"
```

### TaskStatus

Task status enumeration.

```python
class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    BANNED = "banned"
    EXPIRED = "expired"
```

## Data Models

### Task

Task data model containing task information.

```python
@dataclass
class Task:
    task_id: str
    type: str
    status: TaskStatus
    input: Dict[str, Any]
    output: TaskOutput
    progress: int
    create_time: int
    running_left_time: Optional[int] = None
    queuing_num: Optional[int] = None
    error_code: Optional[int] = None
    error_msg: Optional[str] = None

    @property
    def created_at(self) -> datetime.datetime:
        """Get the creation time as a datetime object."""
        return datetime.datetime.fromtimestamp(self.create_time)
```

### TaskOutput

Task output data containing model URLs and other results.

```python
@dataclass
class TaskOutput:
    model: Optional[str] = None
    base_model: Optional[str] = None
    pbr_model: Optional[str] = None
    rendered_image: Optional[str] = None
    riggable: Optional[bool] = None
    rig_type: Optional[RigType] = None
```

### Balance

User balance data model.

```python
@dataclass
class Balance:
    balance: float
    frozen: float
```
