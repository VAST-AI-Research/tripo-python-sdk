"""
Data models for the Tripo API client.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import datetime


class Animation(str, Enum):
    """Available preset animations for retargeting."""
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


class PostStyle(str, Enum):
    """Available styles for model postprocessing."""
    # Stylization styles
    LEGO = "lego"
    VOXEL = "voxel"
    VORONOI = "voronoi"
    MINECRAFT = "minecraft"

class TaskStatus(str, Enum):
    """Task status enum."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    BANNED = "banned"
    EXPIRED = "expired"

    @classmethod
    def from_wire(cls, value: Optional[str]) -> "TaskStatus":
        if isinstance(value, cls):
            return value
        if not value:
            return cls.UNKNOWN
        try:
            return cls(str(value).lower())
        except ValueError:
            return cls.UNKNOWN

    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATUSES


_TERMINAL_STATUSES = frozenset({
    TaskStatus.SUCCESS,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.BANNED,
    TaskStatus.EXPIRED,
})

class RigType(str, Enum):
    BIPED = "biped"
    QUADRUPED = "quadruped"
    HEXAPOD = "hexapod"
    OCTOPOD = "octopod"
    AVIAN = "avian"
    SERPENTINE = "serpentine"
    AQUATIC = "aquatic"
    OTHERS = "others"

class RigSpec(str, Enum):
    MIXAMO = "mixamo"
    TRIPO = "tripo"
    ACTORCORE = "actorcore"
    UNITY = "unity"
    UNREAL = "unreal"
    VRM = "vrm"


def _first(data: Dict[str, Any], *keys: str) -> Optional[Any]:
    for key in keys:
        value = data.get(key)
        if value:
            return value
    return None


@dataclass
class TaskOutput:
    """Task output data.

    apiv3 returns a single signed ``model_url``; ``model`` and ``pbr_model`` are kept as
    aliases of it so code written against 0.x keeps working.
    """
    model: Optional[str] = None
    base_model: Optional[str] = None
    pbr_model: Optional[str] = None
    rendered_image: Optional[str] = None
    riggable: Optional[bool] = None
    rig_type: Optional[RigType] = None
    # Image outputs (generate_image / text_to_image / generate_multiview_image)
    image: Optional[str] = None
    front_view_url: Optional[str] = None
    left_view_url: Optional[str] = None
    back_view_url: Optional[str] = None
    right_view_url: Optional[str] = None
    # apiv3 fields
    model_url: Optional[str] = None
    rendered_image_url: Optional[str] = None
    generated_image_url: Optional[str] = None
    depth_image_url: Optional[str] = None
    uv_render_url: Optional[str] = None
    rendered_video_url: Optional[str] = None
    topology: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def urls(self) -> Dict[str, str]:
        """Every top-level ``*_url`` field returned by the API."""
        return {
            key: value for key, value in self.raw.items()
            if key.endswith("_url") and isinstance(value, str) and value
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'TaskOutput':
        data = data if isinstance(data, dict) else {}
        multiview = data.get('generate_multiview_image')
        multiview = multiview if isinstance(multiview, dict) else {}
        model_url = _first(data, 'model_url', 'pbr_model_url', 'model', 'pbr_model')
        rendered = _first(data, 'rendered_image_url', 'rendered_image')
        image = _first(data, 'generated_image_url', 'generated_image', 'image_url', 'image')
        topology = data.get('topology')
        return cls(
            model=_first(data, 'model', 'model_url', 'pbr_model_url'),
            base_model=_first(data, 'base_model', 'base_model_url'),
            pbr_model=_first(data, 'pbr_model', 'pbr_model_url', 'model_url'),
            rendered_image=rendered,
            riggable=data.get('riggable'),
            # apiv3 rig-check reports the detected skeleton as ``topology``.
            rig_type=data.get('rig_type') or topology,
            image=image,
            front_view_url=multiview.get('front_view_url'),
            left_view_url=multiview.get('left_view_url'),
            back_view_url=multiview.get('back_view_url'),
            right_view_url=multiview.get('right_view_url'),
            model_url=model_url,
            rendered_image_url=rendered,
            generated_image_url=image,
            depth_image_url=data.get('depth_image_url'),
            uv_render_url=data.get('uv_render_url'),
            rendered_video_url=data.get('rendered_video_url'),
            topology=topology,
            raw=dict(data),
        )


def _iso_to_epoch(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return int(parsed.timestamp())
    return 0


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Task:
    """Task data model."""
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
    completed_at: Optional[str] = None
    credits_consumed: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def created_at(self) -> datetime.datetime:
        """Get the creation time as a datetime object."""
        return datetime.datetime.fromtimestamp(self.create_time)

    @property
    def error_message(self) -> Optional[str]:
        return self.error_msg

    def is_terminal(self) -> bool:
        return TaskStatus.from_wire(self.status).is_terminal()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """Create a Task from an apiv3 (or legacy v2) task payload."""
        create_time = data.get('create_time')
        if create_time is None:
            create_time = _iso_to_epoch(data.get('created_at'))
        progress = data.get('progress')
        task_input = data.get('input')
        return cls(
            task_id=str(data.get('task_id', '')),
            type=data.get('type') or '',
            status=TaskStatus.from_wire(data.get('status')),
            input=task_input if isinstance(task_input, dict) else {},
            output=TaskOutput.from_dict(data.get('output')),
            progress=int(progress) if isinstance(progress, (int, float)) else 0,
            create_time=int(create_time or 0),
            running_left_time=data.get('running_left_time'),
            queuing_num=data.get('queuing_num'),
            error_code=data.get('error_code'),
            error_msg=data.get('error_msg') or data.get('error_message'),
            completed_at=data.get('completed_at'),
            credits_consumed=_as_float(data.get('credits_consumed')),
            raw=dict(data),
        )


@dataclass
class Balance:
    """User balance data model."""
    balance: float
    frozen: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Balance':
        """Create a Balance from a dictionary."""
        return cls(
            balance=float(data.get('balance') or 0),
            frozen=float(data.get('frozen') or 0),
        )


@dataclass
class BatchTaskResult:
    """``POST /v3/tasks/list`` result."""
    tasks: Dict[str, Task]
    missed: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BatchTaskResult':
        raw_tasks = data.get('tasks') or {}
        tasks = {
            task_id: Task.from_dict(payload)
            for task_id, payload in raw_tasks.items()
            if isinstance(payload, dict)
        }
        return cls(tasks=tasks, missed=list(data.get('missed') or []))


@dataclass
class TaskUsageItem:
    """One row of ``GET /v3/account/usage``."""
    task_id: str
    type: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    credits_consumed: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskUsageItem':
        return cls(
            task_id=str(data.get('task_id', '')),
            type=data.get('type'),
            status=data.get('status'),
            created_at=data.get('created_at'),
            credits_consumed=_as_float(data.get('credits_consumed')),
        )


@dataclass
class PresignedUpload:
    """``POST /v3/files/presign`` result."""
    file_token: str
    upload_url: str
    expires_in: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PresignedUpload':
        return cls(
            file_token=str(data.get('file_token') or ''),
            upload_url=str(data.get('presigned_url') or data.get('upload_url') or ''),
            expires_in=data.get('expires_in'),
        )
