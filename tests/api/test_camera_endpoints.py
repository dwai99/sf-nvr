"""API tests for camera endpoints"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import json


@pytest.mark.api
class TestCameraEndpoints:
    """Test camera-related API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client for API"""
        # Note: This requires the actual app to be importable
        # In real implementation, you'd import from your main app file
        pytest.skip("Requires full app integration - implement with actual app instance")

    def test_get_cameras_list(self, client):
        """Test GET /api/cameras endpoint"""
        response = client.get("/api/cameras")

        assert response.status_code == 200
        cameras = response.json()
        assert isinstance(cameras, list)
        assert len(cameras) > 0

        # Verify camera structure
        camera = cameras[0]
        required_fields = ['id', 'name', 'rtsp_url', 'enabled', 'is_recording']
        for field in required_fields:
            assert field in camera

    def test_get_camera_health_all(self, client):
        """Test GET /api/cameras/health endpoint"""
        response = client.get("/api/cameras/health")

        assert response.status_code == 200
        health_data = response.json()
        assert isinstance(health_data, list)

        if len(health_data) > 0:
            camera_health = health_data[0]
            required_fields = [
                'camera_name',
                'status',
                'is_recording',
                'last_frame_time',
                'total_reconnects'
            ]
            for field in required_fields:
                assert field in camera_health

    def test_get_camera_health_specific(self, client):
        """Test GET /api/cameras/{name}/health endpoint"""
        camera_name = "Test Camera 1"
        response = client.get(f"/api/cameras/{camera_name}/health")

        if response.status_code == 200:
            health = response.json()
            assert health['camera_name'] == camera_name
            assert 'status' in health
            assert health['status'] in ['healthy', 'degraded', 'stale', 'stopped']

    def test_get_camera_health_not_found(self, client):
        """Test health endpoint with non-existent camera"""
        response = client.get("/api/cameras/NonExistentCamera/health")

        assert response.status_code == 404

    def test_camera_start_stop(self, client):
        """Test camera start/stop endpoints"""
        camera_name = "Test Camera 1"

        # Stop camera
        response = client.post(f"/api/cameras/{camera_name}/stop")
        assert response.status_code in [200, 204]

        # Verify stopped
        response = client.get("/api/cameras")
        cameras = response.json()
        test_camera = next(c for c in cameras if c['name'] == camera_name)
        assert test_camera['is_recording'] is False

        # Start camera
        response = client.post(f"/api/cameras/{camera_name}/start")
        assert response.status_code in [200, 204]

        # Verify started
        response = client.get("/api/cameras")
        cameras = response.json()
        test_camera = next(c for c in cameras if c['name'] == camera_name)
        assert test_camera['is_recording'] is True


@pytest.mark.api
class TestStorageEndpoints:
    """Test storage-related API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client for API"""
        pytest.skip("Requires full app integration")

    def test_get_storage_stats(self, client):
        """Test GET /api/storage/stats endpoint"""
        response = client.get("/api/storage/stats")

        assert response.status_code == 200
        stats = response.json()

        required_fields = ['cameras', 'total_size_gb', 'total_files']
        for field in required_fields:
            assert field in stats

        # Verify per-camera stats structure
        if 'cameras' in stats and len(stats['cameras']) > 0:
            camera_stats = stats['cameras'][0]
            assert 'camera_name' in camera_stats
            assert 'size_gb' in camera_stats
            assert 'file_count' in camera_stats

    def test_get_cleanup_status(self, client):
        """Test GET /api/storage/cleanup/status endpoint"""
        response = client.get("/api/storage/cleanup/status")

        assert response.status_code == 200
        status = response.json()

        required_fields = [
            'disk_usage_percent',
            'disk_free_gb',
            'cleanup_threshold',
            'retention_days'
        ]
        for field in required_fields:
            assert field in status

    def test_manual_cleanup_trigger(self, client):
        """Test POST /api/storage/cleanup/run endpoint"""
        response = client.post("/api/storage/cleanup/run")

        assert response.status_code == 200
        result = response.json()

        required_fields = [
            'cleanup_triggered',
            'files_deleted',
            'space_freed_gb'
        ]
        for field in required_fields:
            assert field in result


@pytest.mark.api
class TestAlertEndpoints:
    """Test alert-related API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client for API"""
        pytest.skip("Requires full app integration")

    def test_get_all_alerts(self, client):
        """Test GET /api/alerts endpoint"""
        response = client.get("/api/alerts")

        assert response.status_code == 200
        alerts = response.json()
        assert isinstance(alerts, list)

    def test_get_alerts_with_limit(self, client):
        """Test GET /api/alerts with limit parameter"""
        limit = 10
        response = client.get(f"/api/alerts?limit={limit}")

        assert response.status_code == 200
        alerts = response.json()
        assert len(alerts) <= limit

    def test_get_camera_alerts(self, client):
        """Test GET /api/alerts/camera/{name} endpoint"""
        camera_name = "Test Camera 1"
        response = client.get(f"/api/alerts/camera/{camera_name}")

        assert response.status_code == 200
        alerts = response.json()
        assert isinstance(alerts, list)

        # All alerts should be for the specified camera
        for alert in alerts:
            if alert.get('camera_name'):
                assert alert['camera_name'] == camera_name


@pytest.mark.api
class TestPlaybackEndpoints:
    """Test playback-related API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client for API"""
        pytest.skip("Requires full app integration")

    def test_get_recordings_by_date(self, client):
        """Test GET /api/playback/recordings endpoint"""
        start_time = "2026-01-20T12:00:00"
        end_time = "2026-01-20T13:00:00"

        response = client.get(
            f"/api/playback/recordings?start_time={start_time}&end_time={end_time}"
        )

        assert response.status_code == 200
        data = response.json()

        assert 'cameras' in data
        assert isinstance(data['cameras'], dict)

    def test_get_available_dates(self, client):
        """Test GET /api/playback/dates/{camera_name} endpoint"""
        camera_name = "Test Camera 1"
        response = client.get(f"/api/playback/dates/{camera_name}")

        assert response.status_code == 200
        dates = response.json()
        assert isinstance(dates, list)

        # Dates should be in YYYY-MM-DD format
        if len(dates) > 0:
            date_str = dates[0]
            datetime.strptime(date_str, "%Y-%m-%d")  # Should not raise

    def test_get_motion_events(self, client):
        """Test GET /api/motion/events endpoint"""
        camera_name = "Test Camera 1"
        start_time = "2026-01-20T12:00:00"
        end_time = "2026-01-20T13:00:00"

        response = client.get(
            f"/api/motion/events?camera={camera_name}&start_time={start_time}&end_time={end_time}"
        )

        if response.status_code == 200:
            events = response.json()
            assert isinstance(events, list)

            if len(events) > 0:
                event = events[0]
                assert 'timestamp' in event
                assert 'intensity' in event

    def test_get_motion_heatmap(self, client):
        """Test GET /api/motion/heatmap/{camera_name} endpoint"""
        camera_name = "Test Camera 1"
        date = "2026-01-20"

        response = client.get(f"/api/motion/heatmap/{camera_name}?date={date}")

        if response.status_code == 200:
            # Should return PNG image
            assert response.headers['content-type'] == 'image/png'
            assert len(response.content) > 0
        elif response.status_code == 404:
            # No motion data available is also valid
            pass
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")


@pytest.mark.api
class TestSettingsEndpoints:
    """Test settings-related API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client for API"""
        pytest.skip("Requires full app integration")

    def test_update_motion_settings(self, client):
        """Test POST /api/cameras/{name}/motion-settings endpoint"""
        camera_name = "Test Camera 1"
        settings = {
            "sensitivity": 30,
            "min_area": 600
        }

        response = client.post(
            f"/api/cameras/{camera_name}/motion-settings",
            json=settings
        )

        assert response.status_code == 200

    def test_update_motion_settings_invalid_data(self, client):
        """Test motion settings with invalid data"""
        camera_name = "Test Camera 1"
        invalid_settings = {
            "sensitivity": -10,  # Invalid: negative
            "min_area": "not_a_number"  # Invalid: wrong type
        }

        response = client.post(
            f"/api/cameras/{camera_name}/motion-settings",
            json=invalid_settings
        )

        # Should reject invalid data
        assert response.status_code in [400, 422]
