"""
Unit tests for data models.
"""

import datetime

from tripo3d.models import Balance, BatchTaskResult, RigSpec, Task, TaskOutput, TaskStatus, TaskUsageItem


V3_TASK = {
    "task_id": "6ffdb041-55c6-4a16-8985-7cc3268a545b",
    "type": "text_to_model",
    "status": "success",
    "progress": 100,
    "input": {"prompt": "a cat"},
    "output": {
        "model_url": "https://cdn.example.com/a/tripo_pbr_model.glb?sig=1",
        "rendered_image_url": "https://cdn.example.com/a/rendered.webp?sig=1",
    },
    "created_at": "2026-10-15T00:00:00Z",
    "completed_at": "2026-10-15T00:01:00Z",
    "credits_consumed": 30,
    "error_code": None,
    "error_message": None,
}


class TestTaskOutput:
    def test_v3_model_url_is_exposed_under_legacy_names(self):
        output = TaskOutput.from_dict(V3_TASK["output"])
        assert output.model_url == V3_TASK["output"]["model_url"]
        assert output.model == output.model_url
        assert output.pbr_model == output.model_url
        assert output.base_model is None
        assert output.rendered_image == V3_TASK["output"]["rendered_image_url"]

    def test_v2_shape_still_parses(self):
        output = TaskOutput.from_dict({
            "model": "m.glb", "base_model": "b.glb", "pbr_model": "p.glb", "rendered_image": "r.png",
            "generated_image": "g.png",
        })
        assert output.model == "m.glb"
        assert output.base_model == "b.glb"
        assert output.pbr_model == "p.glb"
        assert output.image == "g.png"

    def test_rig_check_topology_maps_to_rig_type(self):
        output = TaskOutput.from_dict({"riggable": True, "topology": "quadruped"})
        assert output.riggable is True
        assert output.rig_type == "quadruped"
        assert output.topology == "quadruped"

    def test_explicit_rig_type_wins_over_topology(self):
        assert TaskOutput.from_dict({"rig_type": "biped", "topology": "others"}).rig_type == "biped"

    def test_generated_image_url_and_multiview(self):
        output = TaskOutput.from_dict({
            "generated_image_url": "https://x/g.png",
            "generate_multiview_image": {
                "front_view_url": "f", "left_view_url": "l", "back_view_url": "b", "right_view_url": "r",
            },
        })
        assert output.image == "https://x/g.png"
        assert output.generated_image_url == "https://x/g.png"
        assert (output.front_view_url, output.left_view_url, output.back_view_url, output.right_view_url) == (
            "f", "l", "b", "r")

    def test_new_v3_fields_and_urls(self):
        output = TaskOutput.from_dict({
            "model_url": "m", "uv_render_url": "uv", "depth_image_url": "d",
            "rendered_video_url": "v", "riggable": False,
        })
        assert output.uv_render_url == "uv"
        assert output.depth_image_url == "d"
        assert output.rendered_video_url == "v"
        assert output.urls == {"model_url": "m", "uv_render_url": "uv", "depth_image_url": "d",
                               "rendered_video_url": "v"}

    def test_none_and_non_dict(self):
        assert TaskOutput.from_dict(None).model is None
        assert TaskOutput.from_dict([]).raw == {}


class TestTask:
    def test_from_v3_payload(self):
        task = Task.from_dict(V3_TASK)
        assert task.status == TaskStatus.SUCCESS
        assert task.status == "success"
        assert task.progress == 100
        assert task.create_time == int(datetime.datetime(2026, 10, 15, tzinfo=datetime.timezone.utc).timestamp())
        assert task.completed_at == "2026-10-15T00:01:00Z"
        assert task.credits_consumed == 30.0
        assert task.is_terminal()
        assert isinstance(task.created_at, datetime.datetime)

    def test_error_message_maps_to_error_msg(self):
        task = Task.from_dict({"task_id": "t", "status": "failed", "error_code": 2008,
                               "error_message": "Content moderation violation"})
        assert task.error_code == 2008
        assert task.error_msg == "Content moderation violation"
        assert task.error_message == task.error_msg

    def test_legacy_payload(self):
        task = Task.from_dict({"task_id": "t", "type": "x", "status": "running", "input": {}, "output": {},
                               "progress": 40, "create_time": 1700000000, "running_left_time": 5})
        assert task.create_time == 1700000000
        assert task.running_left_time == 5
        assert not task.is_terminal()

    def test_unknown_status_and_missing_fields(self):
        task = Task.from_dict({"task_id": "t", "status": "weird", "progress": None, "input": "x"})
        assert task.status == TaskStatus.UNKNOWN
        assert task.progress == 0
        assert task.input == {}
        assert task.create_time == 0
        assert not task.is_terminal()

    def test_terminal_statuses(self):
        for status in ("success", "failed", "cancelled", "banned", "expired"):
            assert TaskStatus.from_wire(status).is_terminal()
        for status in ("queued", "running", "unknown", None, ""):
            assert not TaskStatus.from_wire(status).is_terminal()

    def test_bad_created_at(self):
        assert Task.from_dict({"task_id": "t", "status": "queued", "created_at": "not-a-date"}).create_time == 0


class TestOtherModels:
    def test_balance(self):
        balance = Balance.from_dict({"balance": "47725.00", "frozen": None})
        assert balance.balance == 47725.0
        assert balance.frozen == 0.0

    def test_batch(self):
        result = BatchTaskResult.from_dict({"tasks": {"a": {"task_id": "a", "status": "success"}, "b": None},
                                            "missed": ["c"]})
        assert list(result.tasks) == ["a"]
        assert result.missed == ["c"]

    def test_usage_item(self):
        item = TaskUsageItem.from_dict({"task_id": "a", "credits_consumed": "1.5"})
        assert item.credits_consumed == 1.5

    def test_rig_spec_values(self):
        assert {s.value for s in RigSpec} == {"mixamo", "tripo", "actorcore", "unity", "unreal", "vrm"}
