"""
Contract test: the published ComfyUI-Tripo v1.3.1.1 nodes must keep working on this SDK.

``fixtures/comfyui_tripo_v1_3_1_1.py`` is the unmodified ``__init__.py`` of that tag
(sha256 a23de81b479df68017ae4aba9f561e6e8e0d4105b0a3337c9e0a1300a0fb2f6c). Its dependency is
``tripo3d>=0.4.2`` with no upper bound, so users who upgrade the SDK alone run exactly this code.
"""

import importlib.util
import os
import sys
import types
import uuid
import warnings

import pytest

import tripo3d.client as client_module
from tripo3d.exceptions import TripoAPIError, TripoRequestError

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "comfyui_tripo_v1_3_1_1.py")
API_KEY = "tsk_legacy_contract"


# Server-side allow-lists copied from apiv3 (ModelPostProcessValidation / AnimationRequestValidation /
# TextImageModelValidation). The fake rejects anything else, exactly like production does.
ALLOWED_MODELS = {
    "/v3/mesh/decimate": {"v1.0", "v2.0", "v3.0"},
    "/v3/animations/rig": {"v1.0-20240301", "v2.5-20260210", "v3.0-20260909"},
    "/v3/mesh/segment": {"v1.0-20250506", "v2.0-20260430"},
    "/v3/models/texture": {"v2.5-20250123", "v3.0-20250812", "v3.5-20260815"},
    "/v3/generation/text-to-model": {"v3.1-20260211", "v3.0-20250812", "v2.5-20250123", "P1-20260311",
                                     "P2-20260801", "v1.4-20240625"},
    "/v3/generation/image-to-model": {"v3.1-20260211", "v3.0-20250812", "v2.5-20250123", "P1-20260311",
                                      "P2-20260801", "v1.4-20240625"},
    "/v3/generation/multiview-to-model": {"v3.1-20260211", "v3.0-20250812", "v2.5-20250123", "P1-20260311",
                                          "P2-20260801"},
}


class FakeApiv3:
    """Minimal apiv3: validates models like production, then tasks finish immediately."""

    def __init__(self, global_ok=True):
        self.global_ok = global_ok
        self.created = []
        self.tasks = {}
        self.uploads = []
        self.base_urls = []

    def backend(self, api_key, base_url, verify_ssl=True):
        self.base_urls.append(base_url)
        return _Backend(self, base_url)


class _Backend:
    def __init__(self, server, base_url):
        self.server = server
        self.base_url = base_url

    async def request(self, method, path, *, params=None, json_data=None):
        if path == "/v3/account/balance":
            if not self.server.global_ok and self.base_url.endswith(".ai"):
                raise TripoRequestError(401, "unauthorized")
            return {"balance": 100.0, "frozen": 0.0}
        if method == "POST":
            model = (json_data or {}).get("model")
            if model is not None and path in ALLOWED_MODELS and model not in ALLOWED_MODELS[path]:
                raise TripoAPIError(1004, f"invalid model '{model}'")
            task_id = str(uuid.uuid4())
            self.server.created.append((path, json_data))
            if path == "/v3/animations/rig-check":
                output = {"riggable": True, "topology": "biped"}
            else:
                output = {"model_url": f"https://cdn.example.com/{task_id}/tripo_pbr_model.glb?sig=1",
                          "rendered_image_url": f"https://cdn.example.com/{task_id}/r.webp?sig=1"}
            self.server.tasks[task_id] = {"task_id": task_id, "type": path, "status": "success",
                                          "progress": 100, "output": output}
            return {"task_id": task_id, "status": "queued"}
        if method == "GET" and path.startswith("/v3/tasks/"):
            return self.server.tasks[path.rsplit("/", 1)[1]]
        raise AssertionError(f"unexpected {method} {path}")

    async def upload_multipart(self, path, file_path, field_name="file"):
        self.server.uploads.append(file_path)
        return {"file_token": "file_" + uuid.uuid4().hex}

    async def put_file(self, url, file_path, content_type):
        raise AssertionError("small files must not use presign")

    async def download_file(self, url, output_path):
        with open(output_path, "wb") as handle:
            handle.write(b"glTF")

    async def close(self):
        return None


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "chair.glb").write_bytes(b"glTF")

    folder_paths = types.ModuleType("folder_paths")
    folder_paths.get_input_directory = lambda: str(input_dir)
    folder_paths.get_output_directory = lambda: str(output_dir)
    folder_paths.get_annotated_filepath = lambda name: os.path.join(str(input_dir), name)
    folder_paths.filter_files_content_types = lambda files, kinds: [f for f in files if f.endswith(".glb")]
    monkeypatch.setitem(sys.modules, "folder_paths", folder_paths)

    server = FakeApiv3()
    monkeypatch.setattr(client_module, "create_http_backend", server.backend)

    spec = importlib.util.spec_from_file_location("comfyui_tripo_legacy", FIXTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def fake_save_tensor(_tensor, filename):
        path = filename + ".jpg"
        with open(path, "wb") as handle:
            handle.write(b"\xff\xd8\xff")
        return path

    monkeypatch.setattr(module, "save_tensor", fake_save_tensor)
    return types.SimpleNamespace(module=module, server=server, output=output_dir)


def node(legacy, name):
    return legacy.module.NODE_CLASS_MAPPINGS[name]()


def assert_model_file(path, legacy):
    assert path.startswith(str(legacy.output))
    assert path.endswith("_model.glb")
    with open(path, "rb") as handle:
        assert handle.read(4) == b"glTF"


@pytest.mark.asyncio
async def test_full_chain_like_the_published_workflows(legacy):
    server = legacy.server
    gen = node(legacy, "TripoAPIDraft")

    model_file, info = await gen.generate_mesh(
        mode="text_to_model", prompt="a wooden chair", negative_prompt="", apikey=API_KEY,
        model_version="v3.1-20260211", texture=True, pbr=True, image_seed=42, model_seed=42, texture_seed=42,
        texture_quality="standard", geometry_quality="standard", texture_alignment="original_image",
        face_limit=-1, quad=False, compress=False, generate_parts=False, smart_low_poly=False, auto_size=False,
        orientation="default", file_prefix="", output_directory="")
    assert_model_file(model_file, legacy)
    assert server.created[-1] == ("/v3/generation/text-to-model", {
        "prompt": "a wooden chair", "model": "v3.1-20260211", "negative_prompt": "",
        "image_seed": 42, "model_seed": 42, "texture_seed": 42})

    _, image_info = await gen.generate_mesh(
        mode="image_to_model", image=object(), apikey=API_KEY, model_version="v3.0-20250812", texture=True,
        pbr=True, model_seed=42, texture_seed=42, texture_quality="detailed", geometry_quality="standard",
        texture_alignment="original_image", face_limit=-1, quad=False, compress=True, generate_parts=False,
        smart_low_poly=False, auto_size=False, orientation="align_image", file_prefix="", output_directory="")
    path, body = server.created[-1]
    assert path == "/v3/generation/image-to-model"
    assert body["input"].startswith("file_") and body["model"] == "v3.0-20250812"
    assert body["compress"] == "geometry" and body["orientation"] == "align_image"

    await gen.generate_mesh(
        mode="multiview_to_model", image=object(), image_left=None, image_back=object(), image_right=None,
        apikey=API_KEY, model_version="v3.0-20250812", texture=True, pbr=True, model_seed=42, texture_seed=42,
        texture_quality="standard", geometry_quality="standard", texture_alignment="original_image",
        face_limit=-1, quad=False, compress=False, generate_parts=False, smart_low_poly=False, auto_size=False,
        orientation="default", file_prefix="", output_directory="")
    path, body = server.created[-1]
    assert path == "/v3/generation/multiview-to-model"
    assert [v is None for v in body["inputs"]] == [False, True, False, True]

    texture_file, texture_info = await node(legacy, "TripoTextureModel").generate_mesh(
        model_info=info, model_version="v2.5-20250123", texture=True, pbr=True, texture_seed=42,
        texture_quality="standard", texture_alignment="original_image", text_prompt="", image_prompt=None,
        style_image=None, part_names="", compress=False, bake=True)
    assert_model_file(texture_file, legacy)
    assert server.created[-1] == ("/v3/models/texture", {"input": info["task_id"], "model": "v2.5-20250123",
                                                         "texture_seed": 42})

    created_before = len(server.created)
    with pytest.raises(ValueError, match="refine_model is no longer supported"):
        await node(legacy, "TripoRefineModel").generate_mesh(model_info=info)
    assert len(server.created) == created_before

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rig_file, rig_info = await node(legacy, "TripoAnimateRigNode").generate_mesh(
            model_info=texture_info, model_version="v2.0-20250506", out_format="glb", spec="tripo")
    assert_model_file(rig_file, legacy)
    assert server.created[-2] == ("/v3/animations/rig-check", {"input": texture_info["task_id"]})
    assert server.created[-1] == ("/v3/animations/rig", {"input": texture_info["task_id"],
                                                         "model": "v2.5-20260210"})

    retarget_file, retarget_info = await node(legacy, "TripoAnimateRetargetNode").generate_mesh(
        model_info=rig_info, animation="preset:walk", out_format="glb", bake_animation=True,
        export_with_geometry=False)
    assert_model_file(retarget_file, legacy)
    assert server.created[-1] == ("/v3/animations/retarget", {"input": rig_info["task_id"],
                                                              "animation": "preset:walk"})

    converted = await node(legacy, "TripoConvertNode").generate_mesh(
        model_info=retarget_info, format="FBX", quad=False, force_symmetry=False, face_limit=-1,
        flatten_bottom=False, flatten_bottom_threshold=0.01, texture_size=4096, texture_format="JPEG",
        pivot_to_center_bottom=False, scale_factor=1.0, with_animation=True, pack_uv=False, bake=True,
        part_names="", fbx_preset="blender", export_vertex_colors=False, export_orientation="+x",
        animate_in_place=False)
    assert_model_file(converted, legacy)
    assert server.created[-1] == ("/v3/models/convert", {"input": retarget_info["task_id"], "format": "FBX"})


@pytest.mark.asyncio
async def test_mesh_nodes(legacy):
    server = legacy.server
    _, info = await node(legacy, "TripoAPIDraft").generate_mesh(
        mode="text_to_model", prompt="robot", apikey=API_KEY, model_version="v3.1-20260211", face_limit=-1,
        file_prefix="", output_directory="")

    seg = node(legacy, "TripoMeshSegmentation")
    _, seg_v1 = await seg.generate_mesh(model_info=info, model_version="v1.0-20250506",
                                        segmentation_granularity="balanced", ref_image=None,
                                        split_by_connectivity=True)
    assert server.created[-1] == ("/v3/mesh/segment", {"input": info["task_id"], "model": "v1.0-20250506"})
    _, seg_v2 = await seg.generate_mesh(model_info=info, model_version="v2.0-20260430",
                                        segmentation_granularity="detailed", ref_image=object(),
                                        split_by_connectivity=False)
    path, body = server.created[-1]
    assert path == "/v3/mesh/segment" and body["model"] == "v2.0-20260430"
    assert body["segmentation_granularity"] == "detailed" and body["split_by_connectivity"] is False
    assert body["ref_image"].startswith("file_")

    complete_file, _ = await node(legacy, "TripoMeshCompletion").generate_mesh(
        model_info=seg_v1, model_version="v1.0-20250506", part_names="")
    assert_model_file(complete_file, legacy)
    assert server.created[-1] == ("/v3/mesh/complete", {"input": seg_v1["task_id"], "model": "v1.0-20250506"})

    await node(legacy, "TripoSmartLowPoly").generate_mesh(
        model_info=info, model_version="P-v2.0-20251225", quad=False, part_names="", face_limit=10000, bake=True)
    assert server.created[-1] == ("/v3/mesh/decimate", {"input": info["task_id"], "model": "v2.0",
                                                        "face_limit": 10000})

    created_before = len(server.created)
    with pytest.raises(ValueError, match="stylize_model is no longer supported"):
        await node(legacy, "TripoStylizeModel").generate_mesh(model_info=info, style="lego", block_size=80)
    assert len(server.created) == created_before


@pytest.mark.asyncio
async def test_import_model_local_file(legacy):
    (result,) = await node(legacy, "TripoImportModel").import_model(
        apikey=API_KEY, model_file="chair.glb", file_prefix="p_", output_directory="", model_url="")
    path, body = legacy.server.created[-1]
    assert path == "/v3/models/import" and body["input"].startswith("file_")
    assert result["file_prefix"] == "p_"


@pytest.mark.asyncio
async def test_region_probe_falls_back_to_cn(legacy, monkeypatch):
    server = FakeApiv3(global_ok=False)
    monkeypatch.setattr(client_module, "create_http_backend", server.backend)
    monkeypatch.setattr(legacy.module, "_tripo_is_global", None)
    client, key = await legacy.module.GetTripoAPI(API_KEY)
    assert key == API_KEY
    assert client.BASE_URL == "https://openapi.tripo3d.com"
    assert legacy.module._tripo_is_global is False


@pytest.mark.asyncio
async def test_control_fake_server_rejects_retired_names(legacy, monkeypatch):
    """Control group: without the SDK mapping the old node values are rejected, as on production."""
    monkeypatch.setattr(client_module, "_LEGACY_LOWPOLY_MODEL_VERSIONS", {})
    monkeypatch.setattr(client_module, "_LEGACY_RIG_MODEL_VERSIONS", {})
    _, info = await node(legacy, "TripoAPIDraft").generate_mesh(
        mode="text_to_model", prompt="robot", apikey=API_KEY, model_version="v3.1-20260211", face_limit=-1,
        file_prefix="", output_directory="")
    with pytest.raises(TripoAPIError):
        await node(legacy, "TripoSmartLowPoly").generate_mesh(
            model_info=info, model_version="P-v2.0-20251225", quad=False, part_names="", face_limit=10000, bake=True)
    with pytest.raises(TripoAPIError):
        await node(legacy, "TripoAnimateRigNode").generate_mesh(
            model_info=info, model_version="v2.0-20250506", out_format="glb", spec="tripo")
