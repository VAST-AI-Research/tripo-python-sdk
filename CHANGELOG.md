# Changelog

## 1.0.0 (2026-10)

The Tripo v2 API is shut down on 2026-10-31. 1.0.0 moves every call to apiv3
(`https://openapi.tripo3d.ai`, China `https://openapi.tripo3d.com`). All 0.x method names,
parameter names and return types are kept; 1.x will not make breaking changes, and deprecated
items are removed only in 2.0.0.

### Changed

- All task methods, task queries, uploads and balance use apiv3 routes. See `docs/API.md`.
- `upload_file` uses `POST /v3/files` (presigned PUT above 50 MB) and always returns
  `{"file_token": ...}`. `boto3` is no longer needed; the `s3` extra is kept empty.
- `download_task_models` downloads the single apiv3 model once; `pbr_model` maps to the same
  file. It also downloads `uv_render`, `depth_image`, `motion` and `rendered_video` when present.
- Rig model `v2.0-20250506` is sent as `v2.5-20260210`, as the v2 API did.
- `smart_lowpoly` / `mesh_decimate` send the apiv3 names `v1.0` / `v2.0` / `v3.0`; the full names
  `P-v1.0-20250506`, `P-v2.0-20251225` (the ComfyUI default), `P-v2.0-20251226` and `P-v3.0-20260909`
  are translated, because apiv3 rejects them. With no `model_version` the server default (v2.0) applies.
- `convert_model` does not send `face_limit` values `<= 0` (meaning "no limit").
- `TaskOutput.rig_type` falls back to the apiv3 `topology` field from rig-check.
- `TaskOutput.model` / `pbr_model` / `rendered_image` / `image` read the apiv3 `*_url` fields.
- Downloads and presigned uploads no longer send the API key to the storage host.
- `GET` requests are retried up to 3 times on 429/502/503/504 and connection errors.
- Fixed the README multiview order: `front, left, back, right`.

### Added

- `mesh_uv` (Smart UV), `text_to_motion`, `image_to_depth`, `image_to_splat`,
  `list_tasks` / `get_tasks`, `get_usage`, `presign_upload`, `download_file`.
- apiv3-style methods: `image_to_image`, `image_to_multiview`, `edit_multiview`, `rig_check`,
  `rig`, `retarget`, `mesh_segment`, `mesh_complete`, `mesh_decimate`.
- `smart_lowpoly(..., smart_uv=)`, `mesh_completion(..., completion_mode=)`,
  `texture_model` accepts `v3.5-20260815` and forwards `delight`.
- `RigSpec` `actorcore`, `unity`, `unreal`, `vrm`.
- `Task.credits_consumed`, `Task.completed_at`, `Task.raw`, `TaskOutput.urls` and the apiv3
  output fields.
- Every method forwards unknown keyword arguments to the API.
- `TripoError` base class, `TripoValidationError`, `TripoPollTimeoutError`.

### Deprecated

- `use_v3=` on `get_task` / `wait_for_task` (ignored).
- `bake_animation` on `retarget_animation` (ignored by apiv3).
- The `s3` extra.

### Removed

- **refine and stylize**: Tripo no longer supports them. `refine_model` / `stylize_model` now raise
  `TripoValidationError` ("no longer supported") without sending a request, and `create_task` rejects the
  `refine_model` / `stylize_model` types. The method names remain only so 0.x callers get that message
  instead of an `AttributeError`.
- The v2 transport (`tripo3d.client_impl`).
- apiv3 no longer serves text/image model `v2.0-20240919`.
