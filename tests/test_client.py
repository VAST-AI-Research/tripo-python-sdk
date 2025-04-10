"""
Unit tests for the TripoClient class.
"""

import os
import pytest
import asyncio
from unittest.mock import patch, MagicMock

from tripo3d import TripoClient, TaskStatus, Task, Balance, TaskOutput, TopologyType
from tripo3d.exceptions import TripoAPIError, TripoRequestError


class TestTripoClient:
    """Test suite for TripoClient."""
    
    @pytest.fixture
    def api_key(self):
        """Fixture for the API key."""
        return "test_api_key"
    
    @pytest.fixture
    def client(self, api_key):
        """Fixture for the TripoClient."""
        return TripoClient(api_key=api_key)
    
    def test_init_with_api_key(self, api_key):
        """Test initializing the client with an API key."""
        client = TripoClient(api_key=api_key)
        assert client.api_key == api_key
        assert client._session is None
    
    def test_init_without_api_key(self):
        """Test initializing the client without an API key."""
        # Set the environment variable
        with patch.dict(os.environ, {"TRIPO_API_KEY": "env_api_key"}):
            client = TripoClient()
            assert client.api_key == "env_api_key"
            assert client._session is None
    
    def test_init_without_api_key_and_env(self):
        """Test initializing the client without an API key and environment variable."""
        # Remove the environment variable if it exists
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as excinfo:
                TripoClient()
            assert "API key is required" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_ensure_session(self, client):
        """Test ensuring that a session exists."""
        session = await client._ensure_session()
        assert session is not None
        assert session.headers["Authorization"] == f"Bearer {client.api_key}"
        
        # Make sure the session is cached
        session2 = await client._ensure_session()
        assert session2 is session
        
        # Clean up
        await client.close()
    
    @pytest.mark.asyncio
    async def test_close(self, client):
        """Test closing the session."""
        session = await client._ensure_session()
        assert session is not None
        
        await client.close()
        assert client._session is None
    
    @pytest.mark.asyncio
    async def test_context_manager(self, api_key):
        """Test using the client as a context manager."""
        async with TripoClient(api_key=api_key) as client:
            assert client._session is not None
            assert not client._session.closed
        
        # Session should be closed after the context manager exits
        assert client._session is None
    
    def test_url(self, client):
        """Test constructing a URL."""
        assert client._url("task") == f"{TripoClient.BASE_URL}/task"
        assert client._url("/task") == f"{TripoClient.BASE_URL}/task"
    
    @pytest.mark.asyncio
    async def test_request_success(self, client):
        """Test making a successful request."""
        # Mock the session and response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json.return_value = {"code": 0, "data": {"key": "value"}}
        
        # Mock the session's request method
        mock_session = MagicMock()
        mock_session.request.return_value.__aenter__.return_value = mock_response
        
        # Mock the ensure_session method
        with patch.object(client, '_ensure_session', return_value=mock_session):
            response = await client._request("GET", "/task")
            
            # Check that the request was made correctly
            mock_session.request.assert_called_once_with(
                method="GET",
                url=f"{TripoClient.BASE_URL}/task",
                params=None,
                json=None,
                data=None,
                headers=None
            )
            
            # Check that the response was parsed correctly
            assert response == {"code": 0, "data": {"key": "value"}}
    
    @pytest.mark.asyncio
    async def test_request_api_error(self, client):
        """Test making a request that returns an API error."""
        # Mock the session and response
        mock_response = MagicMock()
        mock_response.status = 400
        mock_response.text.return_value = '{"code": 2000, "message": "Error message", "suggestion": "Suggestion"}'
        mock_response.json.return_value = {"code": 2000, "message": "Error message", "suggestion": "Suggestion"}
        
        # Mock the session's request method
        mock_session = MagicMock()
        mock_session.request.return_value.__aenter__.return_value = mock_response
        
        # Mock the ensure_session method
        with patch.object(client, '_ensure_session', return_value=mock_session):
            with pytest.raises(TripoAPIError) as excinfo:
                await client._request("GET", "/task")
            
            assert excinfo.value.code == 2000
            assert excinfo.value.message == "Error message"
            assert excinfo.value.suggestion == "Suggestion"
    
    @pytest.mark.asyncio
    async def test_request_http_error(self, client):
        """Test making a request that returns an HTTP error without JSON."""
        # Mock the session and response
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.reason = "Internal Server Error"
        mock_response.text.return_value = "Internal Server Error"
        mock_response.json.side_effect = Exception("Not JSON")
        
        # Mock the session's request method
        mock_session = MagicMock()
        mock_session.request.return_value.__aenter__.return_value = mock_response
        
        # Mock the ensure_session method
        with patch.object(client, '_ensure_session', return_value=mock_session):
            with pytest.raises(TripoRequestError) as excinfo:
                await client._request("GET", "/task")
            
            assert excinfo.value.status_code == 500
            assert "Internal Server Error" in excinfo.value.message
    
    @pytest.mark.asyncio
    async def test_get_task(self, client):
        """Test getting a task."""
        # Mock the response data
        task_data = {
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
        
        # Mock the _request method
        with patch.object(client, '_request', return_value={"code": 0, "data": task_data}):
            task = await client.get_task("task-123")
            
            # Check that the task was returned correctly
            assert isinstance(task, Task)
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
    
    @pytest.mark.asyncio
    async def test_get_balance(self, client):
        """Test getting the user's balance."""
        # Mock the response data
        balance_data = {
            "balance": 100.5,
            "frozen": 10.0
        }
        
        # Mock the _request method
        with patch.object(client, '_request', return_value={"code": 0, "data": balance_data}):
            balance = await client.get_balance()
            
            # Check that the balance was returned correctly
            assert isinstance(balance, Balance)
            assert balance.balance == 100.5
            assert balance.frozen == 10.0
    
    @pytest.mark.asyncio
    async def test_text_to_model(self, client):
        """Test creating a text to model task."""
        # Mock the create_task method
        with patch.object(client, 'create_task', return_value="task-123"):
            task_id = await client.text_to_model(
                prompt="Test prompt",
                negative_prompt="Test negative prompt",
                model_version="v2.5-20250123",
                face_limit=1000,
                texture=True,
                pbr=True,
                text_seed=123,
                model_seed=456,
                texture_seed=789,
                texture_quality="standard",
                style="person:person2cartoon",
                auto_size=True,
                quad=True
            )
            
            # Check that the task ID was returned correctly
            assert task_id == "task-123"
            
            # Check that create_task was called with the correct data
            expected_data = {
                "type": "text_to_model",
                "prompt": "Test prompt",
                "negative_prompt": "Test negative prompt",
                "model_version": "v2.5-20250123",
                "face_limit": 1000,
                "texture": True,
                "pbr": True,
                "text_seed": 123,
                "model_seed": 456,
                "texture_seed": 789,
                "texture_quality": "standard",
                "style": "person:person2cartoon",
                "auto_size": True,
                "quad": True
            }
            client.create_task.assert_called_once_with(expected_data)
    
    @pytest.mark.asyncio
    async def test_text_to_model_minimal(self, client):
        """Test creating a text to model task with minimal parameters."""
        # Mock the create_task method
        with patch.object(client, 'create_task', return_value="task-123"):
            task_id = await client.text_to_model(prompt="Test prompt")
            
            # Check that the task ID was returned correctly
            assert task_id == "task-123"
            
            # Check that create_task was called with the correct data
            expected_data = {
                "type": "text_to_model",
                "prompt": "Test prompt",
                "model_version": "v2.5-20250123",
                "texture": True,
                "pbr": True,
                "auto_size": False,
                "quad": False,
                "texture_quality": "standard"
            }
            client.create_task.assert_called_once_with(expected_data)
    
    @pytest.mark.asyncio
    async def test_text_to_model_empty_prompt(self, client):
        """Test creating a text to model task with an empty prompt."""
        with pytest.raises(ValueError) as excinfo:
            await client.text_to_model(prompt="")
        assert "Prompt is required" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_image_to_model(self, client):
        """Test creating an image to model task."""
        # Mock the upload_file and create_task methods
        with patch.object(client, 'upload_file', return_value="image-token-123"), \
             patch.object(client, 'create_task', return_value="task-123"), \
             patch('os.path.isfile', return_value=True):
            task_id = await client.image_to_model(
                image_path="test.jpg",
                model_version="v2.5-20250123",
                face_limit=1000,
                texture=True,
                pbr=True,
                model_seed=456,
                texture_seed=789,
                texture_quality="standard",
                texture_alignment="original_image",
                style="person:person2cartoon",
                auto_size=True,
                orientation="default",
                quad=True
            )
            
            # Check that the task ID was returned correctly
            assert task_id == "task-123"
            
            # Check that upload_file was called with the correct path
            client.upload_file.assert_called_once_with("test.jpg")
            
            # Check that create_task was called with the correct data
            expected_data = {
                "type": "image_to_model",
                "file": {
                    "type": "image",
                    "file_token": "image-token-123"
                },
                "model_version": "v2.5-20250123",
                "face_limit": 1000,
                "texture": True,
                "pbr": True,
                "model_seed": 456,
                "texture_seed": 789,
                "texture_quality": "standard",
                "texture_alignment": "original_image",
                "style": "person:person2cartoon",
                "auto_size": True,
                "orientation": "default",
                "quad": True
            }
            client.create_task.assert_called_once_with(expected_data)
    
    @pytest.mark.asyncio
    async def test_image_to_model_minimal(self, client):
        """Test creating an image to model task with minimal parameters."""
        # Mock the upload_file and create_task methods
        with patch.object(client, 'upload_file', return_value="image-token-123"), \
             patch.object(client, 'create_task', return_value="task-123"), \
             patch('os.path.isfile', return_value=True):
            task_id = await client.image_to_model(image_path="test.jpg")
            
            # Check that the task ID was returned correctly
            assert task_id == "task-123"
            
            # Check that upload_file was called with the correct path
            client.upload_file.assert_called_once_with("test.jpg")
            
            # Check that create_task was called with the correct data
            expected_data = {
                "type": "image_to_model",
                "file": {
                    "type": "image",
                    "file_token": "image-token-123"
                },
                "model_version": "v2.5-20250123",
                "texture": True,
                "pbr": True,
                "auto_size": False,
                "quad": False,
                "texture_quality": "standard",
                "texture_alignment": "original_image",
                "orientation": "default"
            }
            client.create_task.assert_called_once_with(expected_data)
    
    @pytest.mark.asyncio
    async def test_wait_for_task_success(self, client):
        """Test waiting for a task to complete successfully."""
        # Create mock tasks for the get_task method to return
        running_task = Task(
            task_id="task-123",
            type="text_to_model",
            status=TaskStatus.RUNNING,
            input={"prompt": "Test prompt"},
            output=TaskOutput(),
            progress=50,
            create_time=1625097600
        )
        
        success_task = Task(
            task_id="task-123",
            type="text_to_model",
            status=TaskStatus.SUCCESS,
            input={"prompt": "Test prompt"},
            output=TaskOutput(
                model="https://example.com/model.glb",
                base_model="https://example.com/base_model.glb",
                pbr_model="https://example.com/pbr_model.glb",
                rendered_image="https://example.com/image.png",
                riggable=True,
                topology=TopologyType.BIP
            ),
            progress=100,
            create_time=1625097600
        )
        
        # Mock the get_task method to return the running task and then the success task
        with patch.object(client, 'get_task', side_effect=[running_task, success_task]), \
             patch('asyncio.sleep', return_value=None):
            task = await client.wait_for_task("task-123", polling_interval=0.1)
            
            # Check that the task was returned correctly
            assert task is success_task
            assert task.status == TaskStatus.SUCCESS
            
            # Check that get_task was called twice
            assert client.get_task.call_count == 2
            
            # Check that sleep was called once
            asyncio.sleep.assert_called_once_with(0.1)
    
    @pytest.mark.asyncio
    async def test_wait_for_task_failure(self, client):
        """Test waiting for a task that fails."""
        # Create mock tasks for the get_task method to return
        running_task = Task(
            task_id="task-123",
            type="text_to_model",
            status=TaskStatus.RUNNING,
            input={"prompt": "Test prompt"},
            output=TaskOutput(),
            progress=50,
            create_time=1625097600
        )
        
        failed_task = Task(
            task_id="task-123",
            type="text_to_model",
            status=TaskStatus.FAILED,
            input={"prompt": "Test prompt"},
            output=TaskOutput(),
            progress=50,
            create_time=1625097600
        )
        
        # Mock the get_task method to return the running task and then the failed task
        with patch.object(client, 'get_task', side_effect=[running_task, failed_task]), \
             patch('asyncio.sleep', return_value=None):
            task = await client.wait_for_task("task-123", polling_interval=0.1)
            
            # Check that the task was returned correctly
            assert task is failed_task
            assert task.status == TaskStatus.FAILED
            
            # Check that get_task was called twice
            assert client.get_task.call_count == 2
            
            # Check that sleep was called once
            asyncio.sleep.assert_called_once_with(0.1)
    
    @pytest.mark.asyncio
    async def test_wait_for_task_timeout(self, client):
        """Test waiting for a task that times out."""
        # Create a mock task for the get_task method to return
        running_task = Task(
            task_id="task-123",
            type="text_to_model",
            status=TaskStatus.RUNNING,
            input={"prompt": "Test prompt"},
            output=TaskOutput(),
            progress=50,
            create_time=1625097600
        )
        
        # Mock the get_task method to always return the running task
        # Mock the time to simulate a timeout
        with patch.object(client, 'get_task', return_value=running_task), \
             patch('asyncio.sleep', return_value=None), \
             patch('asyncio.get_event_loop') as mock_loop:
            # Setup the mock loop to return a time that increases each call
            mock_time = MagicMock()
            mock_time.side_effect = [0, 30]  # First call returns 0, second call returns 30
            mock_loop.return_value.time = mock_time
            
            # Wait for the task with a timeout of 10 seconds
            with pytest.raises(asyncio.TimeoutError) as excinfo:
                await client.wait_for_task("task-123", polling_interval=0.1, timeout=10)
            
            assert "did not complete within 10 seconds" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_multiview_to_model(self, client):
        """Test creating a multiview to model task."""
        # Mock the upload_file and create_task methods
        with patch.object(client, 'upload_file', side_effect=["token1", "token2"]), \
             patch.object(client, 'create_task', return_value="task-123"), \
             patch('os.path.isfile', return_value=True):
            task_id = await client.multiview_to_model(
                image_paths=["view1.jpg", "view2.jpg"],
                model_version="v2.5-20250123",
                face_limit=1000,
                texture=True,
                pbr=True,
                model_seed=456,
                texture_seed=789,
                texture_quality="standard",
                texture_alignment="original_image",
                style="person:person2cartoon",
                auto_size=True,
                orientation="default",
                quad=True
            )
            
            # Check that the task ID was returned correctly
            assert task_id == "task-123"
            
            # Check that upload_file was called for each image
            assert client.upload_file.call_count == 2
            
            # Check that create_task was called with the correct data
            expected_data = {
                "type": "multiview_to_model",
                "files": [
                    {"type": "image", "file_token": "token1"},
                    {"type": "image", "file_token": "token2"}
                ],
                "model_version": "v2.5-20250123",
                "face_limit": 1000,
                "texture": True,
                "pbr": True,
                "model_seed": 456,
                "texture_seed": 789,
                "texture_quality": "standard",
                "texture_alignment": "original_image",
                "style": "person:person2cartoon",
                "auto_size": True,
                "orientation": "default",
                "quad": True
            }
            client.create_task.assert_called_once_with(expected_data)

    @pytest.mark.asyncio
    async def test_postprocess(self, client):
        """Test creating a postprocess task."""
        operations = [
            {"type": "smooth", "strength": 0.5},
            {"type": "decimate", "ratio": 0.8}
        ]
        
        with patch.object(client, 'create_task', return_value="task-123"):
            task_id = await client.postprocess(
                model_url="https://example.com/model.glb",
                operations=operations,
                texture=True,
                pbr=True
            )
            
            assert task_id == "task-123"
            
            expected_data = {
                "type": "postprocess",
                "model_url": "https://example.com/model.glb",
                "operations": operations,
                "texture": True,
                "pbr": True
            }
            client.create_task.assert_called_once_with(expected_data)

    @pytest.mark.asyncio
    async def test_stylize(self, client):
        """Test creating a stylize task."""
        with patch.object(client, 'create_task', return_value="task-123"):
            task_id = await client.stylize(
                model_url="https://example.com/model.glb",
                style="person:person2cartoon",
                texture=True,
                pbr=True,
                texture_seed=789,
                texture_quality="standard"
            )
            
            assert task_id == "task-123"
            
            expected_data = {
                "type": "stylize",
                "model_url": "https://example.com/model.glb",
                "style": "person:person2cartoon",
                "texture": True,
                "pbr": True,
                "texture_seed": 789,
                "texture_quality": "standard"
            }
            client.create_task.assert_called_once_with(expected_data)

    @pytest.mark.asyncio
    async def test_texture_model(self, client):
        """Test creating a texture model task."""
        with patch.object(client, 'upload_file', return_value="image-token-123"), \
             patch.object(client, 'create_task', return_value="task-123"), \
             patch('os.path.isfile', return_value=True):
            task_id = await client.texture_model(
                model_url="https://example.com/model.glb",
                texture_prompt="shiny metal surface",
                texture_image_path="texture.jpg",
                pbr=True,
                texture_seed=789,
                texture_quality="standard",
                texture_alignment="original_image"
            )
            
            assert task_id == "task-123"
            
            expected_data = {
                "type": "texture_model",
                "model_url": "https://example.com/model.glb",
                "texture_prompt": "shiny metal surface",
                "texture_image": {
                    "type": "image",
                    "file_token": "image-token-123"
                },
                "pbr": True,
                "texture_seed": 789,
                "texture_quality": "standard",
                "texture_alignment": "original_image"
            }
            client.create_task.assert_called_once_with(expected_data)

    @pytest.mark.asyncio
    async def test_refine(self, client):
        """Test creating a refine task."""
        with patch.object(client, 'create_task', return_value="task-123"):
            task_id = await client.refine(
                model_url="https://example.com/model.glb",
                refinement_type="geometry",
                strength=0.8,
                face_limit=10000,
                texture=True,
                pbr=True
            )
            
            assert task_id == "task-123"
            
            expected_data = {
                "type": "refine",
                "model_url": "https://example.com/model.glb",
                "refinement_type": "geometry",
                "strength": 0.8,
                "face_limit": 10000,
                "texture": True,
                "pbr": True
            }
            client.create_task.assert_called_once_with(expected_data) 