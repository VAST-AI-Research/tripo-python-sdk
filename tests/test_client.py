"""
Unit tests for TripoClient against a recording fake transport.
"""

import asyncio
import os
import warnings

import pytest

from tripo3d import TripoClient
from tripo3d.exceptions import TripoAPIError, TripoPollTimeoutError, TripoRequestError, TripoValidationError
from tripo3d.models import Animation, PostStyle, RigSpec, RigType, Task, TaskStatus

API_KEY = "tsk_test_key"
TASK_ID = "11111111-2222-3333-4444-555555555555"


class FakeBackend:
    """Records calls and replays queued responses (or a default per path)."""

    def __init__(self):
        self.calls = []
        self.queued = {}
        self.uploads = []
        self.puts = []
        self.downloads = []
        self.fail_downloads = set()
        self.closed = False

    def queue(self, method, path, *responses):
        self.queued.setdefault((method, path), []).extend(responses)

    async def request(self, method, path, *, params=None, json_data=None):
        self.calls.append((method, path, json_data, params))
        responses = self.queued.get((method, path))
        if responses:
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if method == "POST":
            return {"task_id": TASK_ID, "type": "x", "status": "queued"}
        return {}

    async def upload_multipart(self, path, file_path, field_name="file"):
        self.uploads.append((path, file_path, field_name))
        return {"file_token": "file_uploaded"}

    async def put_file(self, url, file_path, content_type):
        self.puts.append((url, file_path, content_type))

    async def download_file(self, url, output_path):
        self.downloads.append((url, output_path))
        if url in self.fail_downloads:
            raise TripoRequestError(500, "boom")
        with open(output_path, "wb") as handle:
            handle.write(b"glTF")

    async def close(self):
        self.closed = True


@pytest.fixture
def client():
    c = TripoClient(api_key=API_KEY)
    c._http = FakeBackend()
    return c


def last_call(client):
    return client._http.calls[-1]


def success_task(**output):
    return {"task_id": TASK_ID, "type": "x", "status": "success", "progress": 100, "output": output}


@pytest.fixture
def image_file(tmp_path):
    path = tmp_path / "image.jpg"
    path.write_bytes(b"\xff\xd8\xff")
    return str(path)


class TestInit:
    def test_global_and_cn_base(self):
        assert TripoClient(api_key=API_KEY).BASE_URL == "https://openapi.tripo3d.ai"
        assert TripoClient(api_key=API_KEY, IS_GLOBAL=False).BASE_URL == "https://openapi.tripo3d.com"
        assert TripoClient(API_KEY, True, "https://staging.example/").BASE_URL == "https://staging.example"

    def test_env_key(self, monkeypatch):
        monkeypatch.setenv("TRIPO_API_KEY", API_KEY)
        assert TripoClient().api_key == API_KEY

    def test_missing_or_bad_key_is_value_error(self, monkeypatch):
        monkeypatch.delenv("TRIPO_API_KEY", raising=False)
        with pytest.raises(ValueError):
            TripoClient()
        with pytest.raises(ValueError):
            TripoClient(api_key="tcli_xxx")

    @pytest.mark.asyncio
    async def test_context_manager_closes(self):
        async with TripoClient(api_key=API_KEY) as c:
            fake = FakeBackend()
            c._http = fake
        assert fake.closed


class TestGeneration:
    @pytest.mark.asyncio
    async def test_text_to_model_sends_model_and_only_non_defaults(self, client):
        task_id = await client.text_to_model(prompt="a cat")
        assert task_id == TASK_ID
        assert last_call(client)[:3] == ("POST", "/v3/generation/text-to-model",
                                         {"prompt": "a cat", "model": "v2.5-20250123"})

    @pytest.mark.asyncio
    async def test_text_to_model_full(self, client):
        await client.text_to_model(
            prompt="a cat", negative_prompt="blur", model_version="v3.1-20260211", face_limit=1000,
            texture=False, pbr=True, image_seed=1, model_seed=2, texture_seed=3, texture_quality="detailed",
            quad=True, compress=True, generate_parts=True, smart_low_poly=False, auto_size=True,
            export_orientation="-y",
        )
        assert last_call(client)[2] == {
            "prompt": "a cat", "model": "v3.1-20260211", "negative_prompt": "blur", "face_limit": 1000,
            "texture": False, "image_seed": 1, "model_seed": 2, "texture_seed": 3,
            "texture_quality": "detailed", "auto_size": True, "quad": True, "generate_parts": True,
            "compress": "geometry", "export_orientation": "-y",
        }

    @pytest.mark.asyncio
    async def test_text_to_model_requires_prompt(self, client):
        with pytest.raises(ValueError):
            await client.text_to_model(prompt="")

    @pytest.mark.asyncio
    async def test_extra_kwarg_cannot_override_typed_field(self, client):
        with pytest.raises(TripoValidationError):
            await client.text_to_model(prompt="a", model="v3.1-20260211")
        assert client._http.calls == []

    @pytest.mark.asyncio
    async def test_image_to_model_url_token_task_and_local(self, client, image_file):
        await client.image_to_model("https://x/a.png")
        assert last_call(client)[2] == {"input": "https://x/a.png", "model": "v2.5-20250123"}
        await client.image_to_model("file_abc")
        assert last_call(client)[2]["input"] == "file_abc"
        await client.image_to_model(TASK_ID, model_version="P2-20260801", enable_image_autofix=True,
                                    orientation="align_image", texture_alignment="geometry")
        assert last_call(client)[2] == {"input": TASK_ID, "model": "P2-20260801", "enable_image_autofix": True,
                                        "orientation": "align_image", "texture_alignment": "geometry"}
        await client.image_to_model(image_file)
        assert client._http.uploads == [("/v3/files", image_file, "file")]
        assert last_call(client)[2]["input"] == "file_uploaded"

    @pytest.mark.asyncio
    async def test_image_to_model_missing_local_file(self, client):
        with pytest.raises(FileNotFoundError):
            await client.image_to_model("/nope/missing.png")

    @pytest.mark.asyncio
    async def test_multiview_positional_with_missing_views(self, client, image_file):
        await client.multiview_to_model([image_file, None, "https://x/back.png", None], model_version="v3.0-20250812")
        assert last_call(client)[:3] == ("POST", "/v3/generation/multiview-to-model",
                                         {"inputs": ["file_uploaded", None, "https://x/back.png", None],
                                          "model": "v3.0-20250812"})

    @pytest.mark.asyncio
    async def test_multiview_from_task_and_front_required(self, client):
        await client.multiview_to_model(TASK_ID)
        assert last_call(client)[2]["inputs"] == [{"task_id": TASK_ID}]
        with pytest.raises(TripoValidationError):
            await client.multiview_to_model([None, "https://x/l.png"])

    @pytest.mark.asyncio
    async def test_image_generation_family(self, client):
        await client.text_to_image("a cat", model="seedream_v4", size="1024x1024")
        assert last_call(client)[1:3] == ("/v3/generation/text-to-image",
                                          {"prompt": "a cat", "model": "seedream_v4", "size": "1024x1024"})
        await client.generate_image(prompt="red", model_version="seedream_v5", file="https://x/a.png",
                                    files=["file_b"], t_pose=True)
        assert last_call(client)[1:3] == ("/v3/generation/image-to-image",
                                          {"input": "https://x/a.png", "inputs": ["file_b"], "prompt": "red",
                                           "model": "seedream_v5", "t_pose": True})
        with pytest.raises(TripoValidationError):
            await client.image_to_image(prompt="x")
        await client.generate_multiview_image("https://x/a.png")
        assert last_call(client)[1:3] == ("/v3/generation/image-to-multiview", {"input": "https://x/a.png"})
        prompts = [{"view": "front", "prompt": "red shirt"}]
        await client.edit_multiview_image(TASK_ID, prompts)
        assert last_call(client)[1:3] == ("/v3/generation/edit-multiview", {"input": TASK_ID, "prompts": prompts})
        await client.image_to_splat("https://x/a.png", model_seed=7)
        assert last_call(client)[1:3] == ("/v3/generation/image-to-splat", {"input": "https://x/a.png",
                                                                           "model_seed": 7})
        await client.image_to_depth("https://x/a.png", kind="color", process_res=504)
        assert last_call(client)[1:3] == ("/v3/generation/image-to-depth",
                                          {"input": "https://x/a.png", "kind": "color", "process_res": 504})


class TestPostProcessing:
    @pytest.mark.asyncio
    async def test_texture_model(self, client, image_file):
        await client.texture_model(TASK_ID)
        assert last_call(client)[1:3] == ("/v3/models/texture", {"input": TASK_ID, "model": "v2.5-20250123"})
        await client.texture_model(
            original_model_task_id=TASK_ID, model_version="v3.5-20260815", texture=True, pbr=False,
            texture_seed=42, texture_quality="fast", texture_alignment="geometry", part_names=["a", "b"],
            compress=True, bake=False, text_prompt="wood", image_prompt=image_file, style_image=None,
            delight=True,
        )
        assert last_call(client)[2] == {
            "input": TASK_ID, "model": "v3.5-20260815", "pbr": False, "texture_seed": 42,
            "texture_quality": "fast", "texture_alignment": "geometry", "part_names": ["a", "b"],
            "bake": False, "compress": "geometry",
            "texture_prompt": {"text": "wood", "image": "file_uploaded"}, "delight": True,
        }

    @pytest.mark.asyncio
    async def test_texture_model_drops_empty_prompt(self, client):
        await client.texture_model(TASK_ID, text_prompt=None, image_prompt=None, style_image=None, part_names=None)
        assert "texture_prompt" not in last_call(client)[2]

    @pytest.mark.asyncio
    async def test_convert_model(self, client):
        await client.convert_model(TASK_ID, "FBX", face_limit=-1, texture_format="PNG", with_animation=True,
                                   fbx_preset="mixamo", part_names=None, export_orientation="+x")
        assert last_call(client)[1:3] == ("/v3/models/convert",
                                          {"input": TASK_ID, "format": "FBX", "texture_format": "PNG",
                                           "fbx_preset": "mixamo"})
        await client.convert_model(TASK_ID, "OBJ", face_limit=5000, with_animation=False)
        assert last_call(client)[2] == {"input": TASK_ID, "format": "OBJ", "face_limit": 5000,
                                        "with_animation": False}

    @pytest.mark.asyncio
    async def test_import_model(self, client, tmp_path):
        model = tmp_path / "m.glb"
        model.write_bytes(b"glTF")
        await client.import_model(file=str(model))
        assert last_call(client)[1:3] == ("/v3/models/import", {"input": "file_uploaded"})
        await client.import_model("https://x/m.glb")
        assert last_call(client)[2] == {"input": "https://x/m.glb"}

    @pytest.mark.asyncio
    async def test_refine_and_stylize_are_retired_and_send_nothing(self, client):
        with pytest.raises(TripoValidationError, match="refine_model is no longer supported"):
            await client.refine_model(draft_model_task_id=TASK_ID)
        with pytest.raises(TripoValidationError, match="stylize_model is no longer supported"):
            await client.stylize_model(TASK_ID, PostStyle.LEGO, block_size=80)
        for task_type in ("refine_model", "stylize_model"):
            with pytest.raises(TripoValidationError, match="no longer supported"):
                await client.create_task({"type": task_type, "original_model_task_id": TASK_ID})
        assert client._http.calls == []


class TestAnimation:
    @pytest.mark.asyncio
    async def test_check_riggable(self, client):
        await client.check_riggable(TASK_ID)
        assert last_call(client)[1:3] == ("/v3/animations/rig-check", {"input": TASK_ID})

    @pytest.mark.asyncio
    async def test_rig_model_defaults(self, client):
        await client.rig_model(TASK_ID)
        assert last_call(client)[1:3] == ("/v3/animations/rig", {"input": TASK_ID, "model": "v1.0-20240301"})

    @pytest.mark.asyncio
    async def test_rig_model_legacy_v2_version_is_mapped(self, client):
        with pytest.warns(UserWarning, match="v2.5-20260210"):
            await client.rig_model(original_model_task_id=TASK_ID, out_format="fbx", rig_type="quadruped",
                                   spec="mixamo", model_version="v2.0-20250506")
        assert last_call(client)[2] == {"input": TASK_ID, "model": "v2.5-20260210", "out_format": "fbx",
                                        "rig_type": "quadruped", "spec": "mixamo"}

    @pytest.mark.asyncio
    async def test_rig_native_v3(self, client):
        await client.rig(TASK_ID, model="v3.0-20260909", rig_type=RigType.OTHERS, spec=RigSpec.VRM,
                         no_weights_list=["hair"])
        assert last_call(client)[2] == {"input": TASK_ID, "model": "v3.0-20260909", "rig_type": "others",
                                        "spec": "vrm", "no_weights_list": ["hair"]}

    @pytest.mark.asyncio
    async def test_retarget_animation_single_and_list(self, client):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await client.retarget_animation(original_model_task_id=TASK_ID, animation="preset:walk",
                                            out_format="glb", bake_animation=True, export_with_geometry=False)
        assert last_call(client)[1:3] == ("/v3/animations/retarget", {"input": TASK_ID,
                                                                       "animation": "preset:walk"})
        await client.retarget_animation(TASK_ID, [Animation.RUN, "preset:jump"], out_format="fbx",
                                        export_with_geometry=True)
        assert last_call(client)[2] == {"input": TASK_ID, "animations": ["preset:run", "preset:jump"],
                                        "out_format": "fbx", "export_with_geometry": True}

    @pytest.mark.asyncio
    async def test_retarget_bake_animation_false_warns_and_is_not_sent(self, client):
        with pytest.warns(DeprecationWarning, match="bake_animation"):
            await client.retarget_animation(TASK_ID, "preset:idle", bake_animation=False)
        assert "bake_animation" not in last_call(client)[2]

    @pytest.mark.asyncio
    async def test_retarget_requires_animation(self, client):
        with pytest.raises(TripoValidationError):
            await client.retarget(TASK_ID)

    @pytest.mark.asyncio
    async def test_text_to_motion(self, client):
        segments = [{"prompt": "walk", "frames": 60}]
        await client.text_to_motion(segments, render_video=True)
        assert last_call(client)[1:3] == ("/v3/animations/text-to-motion",
                                          {"segments": segments, "render_video": True})
        with pytest.raises(TripoValidationError):
            await client.text_to_motion([])


class TestMesh:
    @pytest.mark.asyncio
    async def test_segmentation_v1_and_v2(self, client, image_file):
        await client.mesh_segmentation(original_model_task_id=TASK_ID, model_version="v1.0-20250506")
        assert last_call(client)[1:3] == ("/v3/mesh/segment", {"input": TASK_ID, "model": "v1.0-20250506"})
        await client.mesh_segmentation(TASK_ID, model_version="v2.0-20260430", segmentation_granularity="detailed",
                                       split_by_connectivity=False, ref_image=image_file)
        assert last_call(client)[2] == {"input": TASK_ID, "model": "v2.0-20260430",
                                        "segmentation_granularity": "detailed", "ref_image": "file_uploaded",
                                        "split_by_connectivity": False}

    @pytest.mark.asyncio
    async def test_completion(self, client):
        await client.mesh_completion(original_model_task_id=TASK_ID, model_version="v1.0-20250506",
                                     part_names=None)
        assert last_call(client)[1:3] == ("/v3/mesh/complete", {"input": TASK_ID, "model": "v1.0-20250506"})
        await client.mesh_completion(TASK_ID, part_names=["arm"], completion_mode="quick_cap")
        assert last_call(client)[2] == {"input": TASK_ID, "model": "v1.0-20250506", "part_names": ["arm"],
                                        "completion_mode": "quick_cap"}

    @pytest.mark.asyncio
    async def test_smart_lowpoly(self, client):
        await client.smart_lowpoly(original_model_task_id=TASK_ID, model_version="P-v2.0-20251225", quad=False,
                                   part_names=None, face_limit=10000, bake=True)
        assert last_call(client)[1:3] == ("/v3/mesh/decimate", {"input": TASK_ID, "model": "v2.0",
                                                                 "face_limit": 10000})
        for full, short in (("P-v2.0-20251226", "v2.0"), ("P-v3.0-20260909", "v3.0"), ("P-v1.0-20250506", "v1.0"),
                            ("v2.0", "v2.0")):
            await client.smart_lowpoly(TASK_ID, model_version=full)
            assert last_call(client)[2]["model"] == short
        await client.smart_lowpoly(TASK_ID)
        assert "model" not in last_call(client)[2]
        await client.smart_lowpoly(TASK_ID, model_version="v3.0", quad=True, smart_uv=True, bake=False)
        assert last_call(client)[2] == {"input": TASK_ID, "model": "v3.0", "smart_uv": True, "quad": True,
                                        "bake": False}

    @pytest.mark.asyncio
    async def test_mesh_uv(self, client):
        await client.mesh_uv(TASK_ID, export_orientation="+y")
        assert last_call(client)[1:3] == ("/v3/mesh/uv", {"input": TASK_ID, "export_orientation": "+y"})


class TestTasks:
    @pytest.mark.asyncio
    async def test_get_task_and_step(self, client):
        client._http.queue("GET", f"/v3/tasks/{TASK_ID}", success_task(model_url="https://x/m.glb"))
        task = await client.get_task(TASK_ID, use_v3=False)
        assert task.output.model == "https://x/m.glb"
        assert last_call(client)[3] is None
        await client.get_task(TASK_ID, step=1)
        assert last_call(client)[3] == {"step": 1}

    @pytest.mark.asyncio
    async def test_list_tasks(self, client):
        client._http.queue("POST", "/v3/tasks/list", {"tasks": {TASK_ID: success_task()}, "missed": ["z"]})
        result = await client.get_tasks([TASK_ID, "z"])
        assert last_call(client)[2] == {"task_ids": [TASK_ID, "z"]}
        assert list(result.tasks) == [TASK_ID] and result.missed == ["z"]
        with pytest.raises(TripoValidationError):
            await client.list_tasks([])

    @pytest.mark.asyncio
    async def test_create_task_routes_by_type(self, client):
        await client.create_task({"type": "animate_rig", "original_model_task_id": TASK_ID})
        assert last_call(client)[1:3] == ("/v3/animations/rig", {"original_model_task_id": TASK_ID})
        with pytest.raises(TripoValidationError):
            await client.create_task({"type": "nope"})

    @pytest.mark.asyncio
    async def test_unexpected_create_response(self, client):
        client._http.queue("POST", "/v3/mesh/uv", {"status": "queued"})
        with pytest.raises(TripoRequestError):
            await client.mesh_uv(TASK_ID)

    @pytest.mark.asyncio
    async def test_api_error_propagates(self, client):
        client._http.queue("POST", "/v3/animations/rig", TripoAPIError(1004, "invalid model"))
        with pytest.raises(TripoAPIError) as info:
            await client.rig_model(TASK_ID, model_version="v9")
        assert info.value.code == 1004

    @pytest.mark.asyncio
    async def test_wait_for_task_polls_until_terminal(self, client, monkeypatch):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        path = f"/v3/tasks/{TASK_ID}"
        client._http.queue("GET", path, {"task_id": TASK_ID, "status": "queued"},
                           {"task_id": TASK_ID, "status": "running", "progress": 50},
                           {"task_id": TASK_ID, "status": "failed", "error_code": 2008, "error_message": "bad"})
        task = await client.wait_for_task(TASK_ID, verbose=True, use_v3=False)
        assert task.status == TaskStatus.FAILED
        assert task.error_msg == "bad"
        assert sleeps == [2.0, 4.0]

    @pytest.mark.asyncio
    async def test_wait_for_task_interval_is_capped(self, client, monkeypatch):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        client._http.queue("GET", f"/v3/tasks/{TASK_ID}", *([{"task_id": TASK_ID, "status": "running"}] * 6),
                           {"task_id": TASK_ID, "status": "success"})
        await client.wait_for_task(TASK_ID)
        assert sleeps == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0]

    @pytest.mark.asyncio
    async def test_wait_for_task_timeout_is_asyncio_timeout(self, client):
        client._http.queue("GET", f"/v3/tasks/{TASK_ID}", *([{"task_id": TASK_ID, "status": "running"}] * 50))
        with pytest.raises(asyncio.TimeoutError):
            await client.wait_for_task(TASK_ID, polling_interval=0.01, timeout=0.05)
        assert issubclass(TripoPollTimeoutError, asyncio.TimeoutError)

    @pytest.mark.asyncio
    async def test_balance_and_usage(self, client):
        client._http.queue("GET", "/v3/account/balance", {"balance": 10, "frozen": 2})
        balance = await client.get_balance()
        assert (balance.balance, balance.frozen) == (10.0, 2.0)
        client._http.queue("GET", "/v3/account/usage", [{"task_id": "a", "credits_consumed": 3}])
        usage = await client.get_usage(limit=5)
        assert usage[0].credits_consumed == 3.0
        assert last_call(client)[3] == {"limit": 5, "offset": 0}


class TestFiles:
    @pytest.mark.asyncio
    async def test_small_upload_uses_multipart(self, client, image_file):
        assert await client.upload_file(image_file) == {"file_token": "file_uploaded"}
        assert client._http.puts == []

    @pytest.mark.asyncio
    async def test_large_upload_uses_presign(self, client, tmp_path, monkeypatch):
        big = tmp_path / "big.glb"
        big.write_bytes(b"0" * 32)
        monkeypatch.setattr(TripoClient, "MULTIPART_MAX_BYTES", 16)
        client._http.queue("POST", "/v3/files/presign",
                           {"presigned_url": "https://s3/put?sig", "file_token": "file_big", "expires_in": 3600})
        assert await client.upload_file(str(big)) == {"file_token": "file_big"}
        assert client._http.calls[-1][2] == {"format": "glb"}
        assert [put[:2] for put in client._http.puts] == [("https://s3/put?sig", str(big))]
        assert client._http.uploads == []

    @pytest.mark.asyncio
    async def test_presign_incomplete(self, client):
        client._http.queue("POST", "/v3/files/presign", {"file_token": ""})
        with pytest.raises(TripoRequestError):
            await client.presign_upload("png")

    @pytest.mark.asyncio
    async def test_upload_missing(self, client):
        with pytest.raises(FileNotFoundError):
            await client.upload_file("/nope/x.png")

    @pytest.mark.asyncio
    async def test_download_task_models_dedupes_model_url(self, client, tmp_path):
        task = Task.from_dict(success_task(model_url="https://cdn/a/model.glb?s=1",
                                           rendered_image_url="https://cdn/a/r.webp?s=1"))
        result = await client.download_task_models(task, str(tmp_path))
        assert list(result) == ["model", "pbr_model", "rendered_image"]
        assert result["model"] == os.path.join(str(tmp_path), f"{TASK_ID}_model.glb")
        assert result["pbr_model"] == result["model"]
        assert result["rendered_image"].endswith("_rendered.webp")
        assert len(client._http.downloads) == 2

    @pytest.mark.asyncio
    async def test_download_failure_maps_to_none(self, client, tmp_path):
        task = Task.from_dict(success_task(model_url="https://cdn/m.glb", uv_render_url="https://cdn/uv"))
        client._http.fail_downloads.add("https://cdn/uv")
        result = await client.download_task_models(task, str(tmp_path))
        assert result["model"].endswith("_model.glb")
        assert result["uv_render"] is None

    @pytest.mark.asyncio
    async def test_download_requires_success_and_dir(self, client, tmp_path):
        with pytest.raises(ValueError):
            await client.download_task_models(Task.from_dict({"task_id": "t", "status": "failed"}), str(tmp_path))
        with pytest.raises(FileNotFoundError):
            await client.download_task_models(Task.from_dict(success_task()), str(tmp_path / "missing"))

    @pytest.mark.asyncio
    async def test_download_rendered_image(self, client, tmp_path):
        assert await client.download_rendered_image(Task.from_dict(success_task()), str(tmp_path)) is None
        task = Task.from_dict(success_task(rendered_image_url="https://cdn/r.png"))
        path = await client.download_rendered_image(task, str(tmp_path))
        assert path.endswith(f"{TASK_ID}_rendered.png")

    @pytest.mark.asyncio
    async def test_ssl_error_retries_insecure(self, client, tmp_path, monkeypatch):
        import tripo3d.client as client_module

        async def ssl_fail(url, output_path):
            raise TripoRequestError(0, "Download error: [SSL: CERTIFICATE_VERIFY_FAILED]")

        client._http.download_file = ssl_fail
        insecure = FakeBackend()
        seen = {}

        def fake_create(api_key, base_url, verify_ssl=True):
            seen["verify_ssl"] = verify_ssl
            return insecure

        monkeypatch.setattr(client_module, "create_http_backend", fake_create)
        with pytest.warns(UserWarning):
            await client.download_file("https://cdn/m.glb", str(tmp_path / "m.glb"))
        assert seen["verify_ssl"] is False
        assert insecure.downloads and insecure.closed
