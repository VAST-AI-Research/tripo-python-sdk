# Tripo API Reference (tripo3d 1.x, apiv3)

`tripo3d` 1.x talks only to the Tripo **apiv3** API. The v2 API (`api.tripo3d.ai/v2/openapi`)
is shut down on 2026-10-31; 0.x releases stop working at that point.

Method names, parameter names and return types of 0.x are unchanged, so most code only needs
`pip install -U "tripo3d>=1.0.0,<2.0.0"`. See [Migrating from 0.x](#migrating-from-0x).

## TripoClient

```python
from tripo3d import TripoClient

client = TripoClient(api_key="tsk_...")            # global: https://openapi.tripo3d.ai
client = TripoClient(api_key="tsk_...", IS_GLOBAL=False)  # China: https://openapi.tripo3d.com
client = TripoClient()                              # reads TRIPO_API_KEY
```

| Argument | Default | Description |
| --- | --- | --- |
| `api_key` | `TRIPO_API_KEY` | Must start with `tsk_`, otherwise `ValueError` |
| `IS_GLOBAL` | `True` | `False` selects the China endpoint |
| `v3_base_url` | `None` | Override the endpoint (e.g. staging) |
| `verify_ssl` | `True` | Verify TLS for API calls |

All methods are `async`. Use `async with TripoClient() as client:` or call `await client.close()`.

Every task-creating method returns the **task ID** (`str`). Pass it to `wait_for_task`, then use
the returned `Task`. Downstream methods take that task ID as their source model.

### Inputs

Image and model inputs accept any of:

| Value | Example | What the SDK does |
| --- | --- | --- |
| Local path | `"./cat.png"` | Uploads it (see `upload_file`) and sends the `file_token` |
| URL | `"https://.../cat.png"` | Sent as-is; the API fetches it |
| `file_token` | `"file_3f2c..."` | Sent as-is |
| Task ID | `"6ffdb041-55c6-..."` | Sent as-is; the API reuses that task's output |

A string that looks like a path but does not exist raises `FileNotFoundError`.

Methods accept extra keyword arguments that are forwarded to the API unchanged, so new API
parameters can be used before the SDK names them, e.g.
`text_to_model(prompt, model_version="v3.1-20260211", export_orientation="-y")`.

## Route map

| Method | Route |
| --- | --- |
| `text_to_model` | `POST /v3/generation/text-to-model` |
| `image_to_model` | `POST /v3/generation/image-to-model` |
| `multiview_to_model` | `POST /v3/generation/multiview-to-model` |
| `text_to_image` | `POST /v3/generation/text-to-image` |
| `image_to_image` / `generate_image` | `POST /v3/generation/image-to-image` |
| `image_to_multiview` / `generate_multiview_image` | `POST /v3/generation/image-to-multiview` |
| `edit_multiview` / `edit_multiview_image` | `POST /v3/generation/edit-multiview` |
| `image_to_splat` | `POST /v3/generation/image-to-splat` |
| `image_to_depth` | `POST /v3/generation/image-to-depth` |
| `texture_model` | `POST /v3/models/texture` |
| `convert_model` | `POST /v3/models/convert` |
| `import_model` | `POST /v3/models/import` |
| `refine_model`, `stylize_model` | Removed — raise immediately, no request is sent |
| `rig_check` / `check_riggable` | `POST /v3/animations/rig-check` |
| `rig` / `rig_model` | `POST /v3/animations/rig` |
| `retarget` / `retarget_animation` | `POST /v3/animations/retarget` |
| `mesh_segment` / `mesh_segmentation` | `POST /v3/mesh/segment` |
| `mesh_complete` / `mesh_completion` | `POST /v3/mesh/complete` |
| `mesh_decimate` / `smart_lowpoly` | `POST /v3/mesh/decimate` |
| `mesh_uv` | `POST /v3/mesh/uv` |
| `get_task` / `wait_for_task` | `GET /v3/tasks/{task_id}` |
| `list_tasks` / `get_tasks` | `POST /v3/tasks/list` |
| `upload_file` | `POST /v3/files` or `POST /v3/files/presign` + PUT |
| `presign_upload` | `POST /v3/files/presign` |
| `get_balance` | `GET /v3/account/balance` |
| `get_usage` | `GET /v3/account/usage` |
| `create_task` | route chosen by the payload `type` |

Where two names are listed, the first takes apiv3 field names (`input`, `model`) and the second
keeps the 0.x signature.

## Tasks and files

### wait_for_task

```python
task = await client.wait_for_task(task_id, polling_interval=2.0, timeout=None, verbose=False)
```

Polls until the task is `success`, `failed`, `cancelled`, `banned` or `expired`. The interval
starts at `polling_interval` and doubles up to 30 s. `timeout` raises `TripoPollTimeoutError`,
which is an `asyncio.TimeoutError`. A failed task is returned, not raised: check `task.status`,
`task.error_code` and `task.error_msg`.

`use_v3=` is still accepted and ignored.

### get_task / list_tasks

```python
task = await client.get_task(task_id)
batch = await client.list_tasks([id1, id2])   # BatchTaskResult(tasks={id: Task}, missed=[...])
```

### download_task_models

```python
files = await client.download_task_models(task, "./output")
# {"model": "./output/<id>_model.glb", "pbr_model": "./output/<id>_model.glb",
#  "rendered_image": "./output/<id>_rendered.webp"}
```

apiv3 returns a single `model_url`. It is downloaded once; `pbr_model` refers to the same file.
Other outputs that are present are downloaded too: `rendered_image`, `image`,
`front_view`/`left_view`/`back_view`/`right_view`, `uv_render`, `depth_image`,
`rendered_video`. A failed download maps to `None`. Result URLs are signed and expire, so
download promptly. No API key is sent to the download host.

`download_rendered_image(task, output_dir, filename=None)` downloads only the preview image.
`download_file(url, path)` downloads any result URL.

### upload_file

```python
{"file_token": "file_..."} = await client.upload_file("./model.glb")
```

Files up to 50 MB go through `POST /v3/files`; larger files use a presigned PUT. The API limit
is 150 MB. `presign_upload(format)` returns a `PresignedUpload(file_token, upload_url,
expires_in)` if you want to upload yourself.

### get_balance / get_usage

```python
balance = await client.get_balance()          # Balance(balance, frozen)
usage = await client.get_usage(limit=50, offset=0)   # [TaskUsageItem(task_id, type, status, created_at, credits_consumed)]
```

## Generation

### text_to_model

```python
task_id = await client.text_to_model(
    prompt="a cute red panda",
    negative_prompt=None,
    model_version="v2.5-20250123",
    face_limit=None, texture=True, pbr=True,
    image_seed=None, model_seed=None, texture_seed=None,
    texture_quality="standard", geometry_quality="standard",
    auto_size=False, quad=False, compress=False,
    generate_parts=False, smart_low_poly=False, export_uv=True,
)
```

`model_version`: `v3.1-20260211`, `v3.0-20250812`, `v2.5-20250123`, `P1-20260311`,
`P2-20260801`; `v1.4-20240625` is still accepted. `v2.0-20240919` is not available on apiv3.
`texture_quality` also accepts `detailed`. `compress=True` sends `compress: "geometry"`.

### image_to_model

```python
task_id = await client.image_to_model(
    image="./cat.png",
    model_version="v2.5-20250123",
    texture_alignment="original_image", orientation="default",
    enable_image_autofix=False,
    # same quality / topology options as text_to_model
)
```

### multiview_to_model

```python
task_id = await client.multiview_to_model(
    images=["front.png", "left.png", None, "right.png"],   # order: front, left, back, right
    model_version="v3.0-20250812",
)
task_id = await client.multiview_to_model(multiview_task_id)  # output of generate_multiview_image
```

The front view is required; missing views are `None`. `v1.4-20240625` is not available here.

### text_to_image / image_to_image / generate_image

```python
task_id = await client.text_to_image("a red panda")
task_id = await client.image_to_image("./ref.png", prompt="make it blue", model="seedream_v5",
                                      inputs=["./ref2.png"])
task_id = await client.generate_image(prompt="...", model_version=None, file="./ref.png",
                                      files=None, template=None, t_pose=False, sketch_to_render=False)
```

The finished task exposes the image as `task.output.image` (`generated_image_url`).

### image_to_multiview / generate_multiview_image / edit_multiview

```python
task_id = await client.generate_multiview_image("./cat.png")
task_id = await client.edit_multiview_image(task_id, [{"view": "front", "prompt": "red shirt"}])
```

Views are in `task.output.front_view_url`, `left_view_url`, `back_view_url`, `right_view_url`.

### image_to_splat / image_to_depth

```python
task_id = await client.image_to_splat("./cat.png", model_seed=None)
task_id = await client.image_to_depth("./cat.png", kind="gray", process_res=504)
```

## Model post-processing

### texture_model

```python
task_id = await client.texture_model(
    original_model_task_id,
    model_version="v2.5-20250123",          # v2.5-20250123 | v3.0-20250812 | v3.5-20260815
    texture=True, pbr=True, texture_seed=None,
    texture_quality="standard",             # standard | detailed | fast (v3.5 only)
    texture_alignment="original_image",
    part_names=None, compress=False, bake=True,
    text_prompt=None, image_prompt=None, style_image=None,
    delight=None,                           # forwarded, v3.5 option
)
```

### convert_model

```python
task_id = await client.convert_model(
    original_model_task_id, "FBX",          # GLTF | USDZ | FBX | OBJ | STL | 3MF
    quad=False, force_symmetry=False, face_limit=None,
    flatten_bottom=False, flatten_bottom_threshold=0.01,
    texture_size=4096, texture_format="JPEG", scale_factor=1.0,
    pivot_to_center_bottom=False, with_animation=True, pack_uv=False, bake=True,
    part_names=None, export_vertex_colors=False, fbx_preset="blender",
    export_orientation="+x", animate_in_place=False,
)
```

`face_limit` values `<= 0` mean "no limit" and are not sent.

### import_model

```python
task_id = await client.import_model("./chair.glb")      # or a model URL / file_token
```

The import task ID can then be used as `original_model_task_id` everywhere.

### refine_model, stylize_model (removed)

Refine and stylize are no longer supported by Tripo. Both methods still exist so that code written
for 0.x (such as ComfyUI-Tripo 1.3.x) gets a clear `TripoValidationError` (a `ValueError`) saying so,
instead of an `AttributeError`; they never send a request. `create_task` rejects these two types too.
`PostStyle` stays importable for the same reason.

## Animation

### rig_check / check_riggable

```python
check_id = await client.check_riggable(original_model_task_id)
check = await client.wait_for_task(check_id)
check.output.riggable, check.output.rig_type   # e.g. True, "biped"
```

apiv3 reports the detected skeleton as `topology`; the SDK exposes it as `rig_type` too.

### rig / rig_model

```python
task_id = await client.rig_model(original_model_task_id, model_version="v1.0-20240301",
                                 out_format="glb", rig_type=RigType.BIPED, spec=RigSpec.TRIPO)
task_id = await client.rig(original_model_task_id, model="v3.0-20260909",
                           rig_type="others", spec="vrm")
```

`model_version` / `model`: `v1.0-20240301` (default), `v2.5-20260210`, `v3.0-20260909`.
The retired `v2.0-20250506` is sent as `v2.5-20260210` (with a warning), which is what the v2
API did. `spec`: `tripo`, `mixamo`, `actorcore` work with every version; `unity`, `unreal`, `vrm`
need `v2.5-20260210` or `v3.0-20260909` (with `v1.0-20240301` the task fails).

Rig / retarget compatibility measured on the API (2026-10-15); other combinations fail:

| Rig version | Skeleton types it can rig | Humanoid presets | serpentine / aquatic presets | quadruped / hexapod / octopod presets |
| --- | --- | --- | --- | --- |
| `v3.0-20260909` | all | ✓ | ✓ | ✗ |
| `v2.5-20260210` (and `v2.0-20250506`) | all | ✗ | ✓ | ✓ |
| `v1.0-20240301` | biped only | ✓ | — | — |


### retarget / retarget_animation

```python
task_id = await client.retarget_animation(rig_task_id, Animation.WALK, out_format="glb",
                                          export_with_geometry=False, animate_in_place=False)
task_id = await client.retarget(rig_task_id, animations=["preset:walk", "preset:run"])
```

At most 5 animations per task. `bake_animation` is accepted but ignored (apiv3 no longer uses it).
The preset must suit the rig version, see the table under `rig`.

## Mesh

```python
task_id = await client.mesh_segmentation(original_model_task_id, model_version="v2.0-20260430",
                                         segmentation_granularity="balanced",   # simple | balanced | detailed
                                         ref_image="./hint.png", split_by_connectivity=True)
task_id = await client.mesh_completion(segment_task_id, completion_mode="ai_completion")  # or quick_cap
task_id = await client.smart_lowpoly(original_model_task_id, model_version="v3.0",       # v1.0 | v2.0 | v3.0
                                     face_limit=10000, quad=False, smart_uv=True)
task_id = await client.mesh_uv(original_model_task_id)
```

- `mesh_completion` requires a `mesh_segmentation` task as input.
- `smart_lowpoly` face limit: 500–20000 (quad ≤ 10000) for v2.0/v3.0. `smart_uv` needs v3.0.
  The full names `P-v1.0-20250506`, `P-v2.0-20251225`, `P-v2.0-20251226` and `P-v3.0-20260909` are
  translated to `v1.0` / `v2.0` / `v3.0`, the only values apiv3 accepts.
- `mesh_uv` (Smart UV, 20 credits) returns `output.model_url` and `output.uv_render_url`; the
  input must not exceed 80,000 equivalent triangles.

## Data models

### Task

| Field | Description |
| --- | --- |
| `task_id`, `type` | |
| `status` | `TaskStatus` (a `str` enum: `queued`, `running`, `success`, `failed`, `cancelled`, `banned`, `expired`, `unknown`) |
| `progress` | 0–100 |
| `output` | `TaskOutput` |
| `create_time` | Unix seconds; `created_at` property returns a `datetime` |
| `completed_at` | ISO-8601 string |
| `credits_consumed` | Credits charged |
| `error_code`, `error_msg` | Set on failure (`error_message` is an alias) |
| `raw` | The untouched API payload |

### TaskOutput

`model` / `pbr_model` / `model_url` (same URL), `base_model`, `rendered_image`, `image`,
`front_view_url`, `left_view_url`, `back_view_url`, `right_view_url`, `riggable`, `rig_type`,
`topology`, `uv_render_url`, `depth_image_url`, `rendered_video_url`, `raw`, and
`urls` (every `*_url` field).

### Enums

`Animation`, `PostStyle`, `RigType`, `RigSpec`, `TaskStatus` — see `tripo3d.models`.

## Errors

| Exception | When |
| --- | --- |
| `TripoAPIError` | The API returned an error `code` (`code`, `message`, `suggestion`, `request_id`) |
| `TripoRequestError` | HTTP or network failure without an API error body (`status_code`, `message`) |
| `TripoValidationError` | Invalid arguments; also a `ValueError` |
| `TripoPollTimeoutError` | `wait_for_task` timeout; also an `asyncio.TimeoutError` |

All derive from `TripoError`. `TripoApiError` / `TripoNetworkError` are aliases.
`GET` requests are retried up to 3 times on 429/502/503/504 and connection errors; task
creation is never retried.

## Migrating from 0.x

| 0.x | 1.x |
| --- | --- |
| v2 endpoint `api.tripo3d.ai/v2/openapi` | apiv3 `openapi.tripo3d.ai` / `openapi.tripo3d.com` |
| `upload_file` returned `{"object": {...}}` with boto3 | Always `{"file_token": ...}`; `boto3` is no longer used (`tripo3d[s3]` is empty) |
| Separate model / pbr_model downloads | One model file; `pbr_model` points at it |
| `wait_for_task(use_v3=True)` for segmentation v2 | Not needed; accepted and ignored |
| Rig `v2.0-20250506` | Sent as `v2.5-20260210` |
| `smart_lowpoly` model `P-v2.0-20251225` / `P-v3.0-20260909` | Sent as `v2.0` / `v3.0` (apiv3 rejects the full names) |
| `bake_animation` | Ignored |
| `refine_model`, `stylize_model` | No longer supported; raise `TripoValidationError` without calling the API |
| Text/image model `v2.0-20240919` | Not available; use `v2.5-20250123` or newer |
| Status `banned` / `expired` | apiv3 reports both as `failed` with an `error_code` |
