"""
Unit tests for data models.
"""

import pytest
import datetime
from typing import Dict, Any

from tripo3d.models import Task, TaskOutput, TaskStatus, TopologyType, Balance


class TestTaskOutput:
    """Test suite for the TaskOutput class."""
    
    def test_from_dict_with_all_fields(self):
        """Test creating a TaskOutput from a dictionary with all fields."""
        data = {
            "model": "https://example.com/model.glb",
            "base_model": "https://example.com/base_model.glb",
            "pbr_model": "https://example.com/pbr_model.glb",
            "rendered_image": "https://example.com/image.png",
            "riggable": True,
            "topology": "bip"
        }
        
        output = TaskOutput.from_dict(data)
        
        assert output.model == "https://example.com/model.glb"
        assert output.base_model == "https://example.com/base_model.glb"
        assert output.pbr_model == "https://example.com/pbr_model.glb"
        assert output.rendered_image == "https://example.com/image.png"
        assert output.riggable is True
        assert output.topology == TopologyType.BIP
    
    def test_from_dict_with_minimal_fields(self):
        """Test creating a TaskOutput from a dictionary with minimal fields."""
        data = {
            "model": "https://example.com/model.glb"
        }
        
        output = TaskOutput.from_dict(data)
        
        assert output.model == "https://example.com/model.glb"
        assert output.base_model is None
        assert output.pbr_model is None
        assert output.rendered_image is None
        assert output.riggable is None
        assert output.topology is None
    
    def test_from_dict_with_empty_dict(self):
        """Test creating a TaskOutput from an empty dictionary."""
        data = {}
        
        output = TaskOutput.from_dict(data)
        
        assert output.model is None
        assert output.base_model is None
        assert output.pbr_model is None
        assert output.rendered_image is None
        assert output.riggable is None
        assert output.topology is None
    
    def test_from_dict_with_invalid_topology(self):
        """Test creating a TaskOutput with an invalid topology value."""
        data = {
            "topology": "invalid"
        }
        
        output = TaskOutput.from_dict(data)
        
        assert output.topology is None


class TestTask:
    """Test suite for the Task class."""
    
    @pytest.fixture
    def task_data(self) -> Dict[str, Any]:
        """Fixture for task data."""
        return {
            "task_id": "task-123",
            "type": "text_to_model",
            "status": "success",
            "input": {"prompt": "Test prompt"},
            "output": {
                "model": "https://example.com/model.glb",
                "base_model": "https://example.com/base_model.glb",
                "pbr_model": "https://example.com/pbr_model.glb",
                "rendered_image": "https://example.com/image.png",
                "riggable": True,
                "topology": "bip"
            },
            "progress": 100,
            "create_time": 1625097600
        }
    
    def test_from_dict(self, task_data):
        """Test creating a Task from a dictionary."""
        task = Task.from_dict(task_data)
        
        assert task.task_id == "task-123"
        assert task.type == "text_to_model"
        assert task.status == TaskStatus.SUCCESS
        assert task.input == {"prompt": "Test prompt"}
        assert task.output.model == "https://example.com/model.glb"
        assert task.output.base_model == "https://example.com/base_model.glb"
        assert task.output.pbr_model == "https://example.com/pbr_model.glb"
        assert task.output.rendered_image == "https://example.com/image.png"
        assert task.output.riggable is True
        assert task.output.topology == TopologyType.BIP
        assert task.progress == 100
        assert task.create_time == 1625097600
    
    def test_created_at(self):
        """Test the created_at property."""
        task = Task(
            task_id="task-123",
            type="text_to_model",
            status=TaskStatus.SUCCESS,
            input={"prompt": "Test prompt"},
            output=TaskOutput(),
            progress=100,
            create_time=1625097600
        )
        
        assert task.created_at == datetime.datetime.fromtimestamp(1625097600)


class TestBalance:
    """Test suite for the Balance class."""
    
    def test_from_dict(self):
        """Test creating a Balance from a dictionary."""
        data = {
            "balance": 100.5,
            "frozen": 10.0
        }
        
        balance = Balance.from_dict(data)
        
        assert balance.balance == 100.5
        assert balance.frozen == 10.0 