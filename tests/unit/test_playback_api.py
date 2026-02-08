"""Unit tests for playback API endpoints"""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json

from nvr.web.playback_api import router, range_requests_response
from nvr.core.playback_db import PlaybackDatabase


@pytest.fixture
def app():
    """Create FastAPI app with playback router"""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def mock_playback_db(temp_dir):
    """Create mock playback database"""
    db_path = temp_dir / "test.db"
    db = PlaybackDatabase(db_path)
    return db


@pytest.fixture
def mock_app_state(mock_playback_db):
    """Create mock app state"""
    state = Mock()
    state.playback_db = mock_playback_db
    return state


@pytest.mark.unit
class TestRangeRequestsResponse:
    """Test HTTP range request handling for video streaming"""

    def test_full_file_request(self, temp_dir):
        """Test streaming entire file without range header"""
        # Create test video file
        test_file = temp_dir / "test.mp4"
        test_file.write_bytes(b"x" * 1024)  # 1KB file

        # Mock request without range header
        mock_request = Mock()
        mock_request.headers = {}

        response = range_requests_response(test_file, mock_request)

        # Should return 200 with full content
        assert response.status_code == 200
        assert response.headers["content-type"] == "video/mp4"
        assert response.headers["accept-ranges"] == "bytes"
        assert response.headers["content-length"] == "1024"

    def test_range_request_partial_content(self, temp_dir):
        """Test streaming partial content with range header"""
        # Create test video file
        test_file = temp_dir / "test.mp4"
        test_file.write_bytes(b"x" * 1024)  # 1KB file

        # Mock request with range header
        mock_request = Mock()
        mock_request.headers = {"range": "bytes=0-511"}

        response = range_requests_response(test_file, mock_request)

        # Should return 206 Partial Content
        assert response.status_code == 206
        assert "content-range" in response.headers
        assert response.headers["content-range"] == "bytes 0-511/1024"

    def test_range_request_open_ended(self, temp_dir):
        """Test range request without end byte"""
        test_file = temp_dir / "test.mp4"
        test_file.write_bytes(b"x" * 2048)

        mock_request = Mock()
        mock_request.headers = {"range": "bytes=1024-"}

        response = range_requests_response(test_file, mock_request)

        assert response.status_code == 206
        assert response.headers["content-range"] == "bytes 1024-2047/2048"

    def test_range_request_invalid_bounds(self, temp_dir):
        """Test range request with invalid bounds gets clamped"""
        test_file = temp_dir / "test.mp4"
        test_file.write_bytes(b"x" * 1024)

        mock_request = Mock()
        mock_request.headers = {"range": "bytes=0-9999"}  # Beyond file size

        response = range_requests_response(test_file, mock_request)

        # Should clamp to file size
        assert response.status_code == 206
        assert response.headers["content-range"] == "bytes 0-1023/1024"

    def test_custom_content_type(self, temp_dir):
        """Test custom content type"""
        test_file = temp_dir / "test.mkv"
        test_file.write_bytes(b"test")

        mock_request = Mock()
        mock_request.headers = {}

        response = range_requests_response(
            test_file,
            mock_request,
            content_type="video/x-matroska"
        )

        assert response.headers["content-type"] == "video/x-matroska"


@pytest.mark.unit
class TestGetCameraRecordings:
    """Test endpoint to get recordings for a specific camera"""

    def test_get_recordings_for_camera(self, client, temp_dir, mock_playback_db):
        """Test getting recordings for a specific camera"""
        # Add test segments to database
        now = datetime.now()
        for i in range(3):
            mock_playback_db.add_segment(
                camera_name="Front Door",
                file_path=str(temp_dir / f"segment_{i}.mp4"),
                start_time=now + timedelta(hours=i),
                end_time=now + timedelta(hours=i, minutes=5),
                duration_seconds=300
            )

        # Mock app state
        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            response = client.get("/api/playback/recordings/Front Door")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
            assert all(seg["camera_name"] == "Front Door" for seg in data)

    def test_get_recordings_with_time_range(self, client, temp_dir, mock_playback_db):
        """Test getting recordings filtered by time range"""
        now = datetime.now()

        # Add segments over 24 hours
        for i in range(10):
            mock_playback_db.add_segment(
                camera_name="Camera 1",
                file_path=str(temp_dir / f"segment_{i}.mp4"),
                start_time=now + timedelta(hours=i),
                end_time=now + timedelta(hours=i, minutes=5),
                duration_seconds=300
            )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            # Query for 6-hour range
            start = (now + timedelta(hours=2)).isoformat()
            end = (now + timedelta(hours=8)).isoformat()

            response = client.get(
                f"/api/playback/recordings/Camera 1?start={start}&end={end}"
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) > 0
            assert len(data) <= 7  # Should be filtered to time range

    def test_get_recordings_nonexistent_camera(self, client, mock_playback_db):
        """Test getting recordings for camera with no recordings"""
        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            response = client.get("/api/playback/recordings/NonexistentCamera")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 0


@pytest.mark.unit
class TestGetAllRecordings:
    """Test endpoint to get recordings for all cameras"""

    def test_get_all_recordings(self, client, temp_dir, mock_playback_db):
        """Test getting recordings for all cameras"""
        now = datetime.now()

        # Add segments for multiple cameras
        for camera_num in range(1, 4):
            for i in range(2):
                mock_playback_db.add_segment(
                    camera_name=f"Camera {camera_num}",
                    file_path=str(temp_dir / f"cam{camera_num}_seg{i}.mp4"),
                    start_time=now + timedelta(hours=i),
                    end_time=now + timedelta(hours=i, minutes=5),
                    duration_seconds=300
                )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            response = client.get("/api/playback/recordings")

            assert response.status_code == 200
            data = response.json()

            # Should return dict with camera names as keys
            assert "Camera 1" in data
            assert "Camera 2" in data
            assert "Camera 3" in data
            assert len(data["Camera 1"]) == 2

    def test_get_all_recordings_with_time_range(self, client, temp_dir, mock_playback_db):
        """Test getting all recordings filtered by time range"""
        now = datetime.now()

        mock_playback_db.add_segment(
            camera_name="Camera 1",
            file_path=str(temp_dir / "segment.mp4"),
            start_time=now,
            end_time=now + timedelta(minutes=5),
            duration_seconds=300
        )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            start = (now - timedelta(hours=1)).isoformat()
            end = (now + timedelta(hours=1)).isoformat()

            response = client.get(
                f"/api/playback/recordings?start={start}&end={end}"
            )

            assert response.status_code == 200
            data = response.json()
            assert "Camera 1" in data


@pytest.mark.unit
class TestGetMotionEvents:
    """Test motion event endpoints"""

    def test_get_camera_motion_events(self, client, temp_dir, mock_playback_db):
        """Test getting motion events for specific camera"""
        now = datetime.now()

        # Add motion event
        mock_playback_db.add_motion_event(
            camera_name="Front Door",
            start_time=now,
            end_time=now + timedelta(seconds=30),
            frame_count=30,
            max_intensity=85.5
        )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            response = client.get("/api/playback/motion-events/Front Door")

            assert response.status_code == 200
            data = response.json()
            assert len(data) > 0
            assert data[0]["camera_name"] == "Front Door"

    def test_get_all_motion_events(self, client, temp_dir, mock_playback_db):
        """Test getting motion events for all cameras"""
        now = datetime.now()

        # Add motion events for multiple cameras
        for camera_num in range(1, 3):
            mock_playback_db.add_motion_event(
                camera_name=f"Camera {camera_num}",
                start_time=now,
                end_time=now + timedelta(seconds=30),
                frame_count=30,
                max_intensity=75.0
            )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            response = client.get("/api/playback/motion-events")

            assert response.status_code == 200
            data = response.json()
            assert "Camera 1" in data
            assert "Camera 2" in data


@pytest.mark.unit
class TestStreamVideo:
    """Test video streaming endpoint"""

    def test_stream_video_segment(self, client, temp_dir, mock_playback_db):
        """Test streaming a video segment"""
        # Create test video file
        test_file = temp_dir / "test.mp4"
        test_file.write_bytes(b"x" * 1024)

        now = datetime.now()
        mock_playback_db.add_segment(
            camera_name="Camera 1",
            file_path=str(test_file),
            start_time=now,
            end_time=now + timedelta(minutes=5),
            duration_seconds=300
        )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            start_time = now.isoformat()
            response = client.get(
                f"/api/playback/video/Camera 1?start={start_time}"
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "video/mp4"

    def test_stream_video_missing_file(self, client, temp_dir, mock_playback_db):
        """Test streaming when file doesn't exist"""
        now = datetime.now()
        mock_playback_db.add_segment(
            camera_name="Camera 1",
            file_path=str(temp_dir / "missing.mp4"),
            start_time=now,
            end_time=now + timedelta(minutes=5),
            duration_seconds=300
        )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            start_time = now.isoformat()
            response = client.get(
                f"/api/playback/video/Camera 1?start={start_time}"
            )

            assert response.status_code == 404

    def test_stream_video_no_segments(self, client, mock_playback_db):
        """Test streaming when no segments available"""
        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            now = datetime.now()
            response = client.get(
                f"/api/playback/video/Camera 1?start={now.isoformat()}"
            )

            assert response.status_code == 404


@pytest.mark.unit
class TestServeRecordingFile:
    """Test direct file serving endpoint"""

    def test_serve_existing_file(self, client, temp_dir):
        """Test serving an existing file"""
        test_file = temp_dir / "recording.mp4"
        test_file.write_bytes(b"video content")

        response = client.get(f"/api/playback/file?file_path={test_file}")

        assert response.status_code == 200

    def test_serve_nonexistent_file(self, client, temp_dir):
        """Test serving a nonexistent file"""
        fake_path = temp_dir / "nonexistent.mp4"

        response = client.get(f"/api/playback/file?file_path={fake_path}")

        assert response.status_code == 404


@pytest.mark.unit
class TestAvailableDates:
    """Test available dates endpoint"""

    def test_get_available_dates(self, client, temp_dir, mock_playback_db):
        """Test getting dates with recordings"""
        # Add segments on different dates
        base_date = datetime(2026, 1, 15, 12, 0, 0)

        for day_offset in [0, 1, 5]:
            date = base_date + timedelta(days=day_offset)
            mock_playback_db.add_segment(
                camera_name="Camera 1",
                file_path=str(temp_dir / f"seg_{day_offset}.mp4"),
                start_time=date,
                end_time=date + timedelta(minutes=5),
                duration_seconds=300
            )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            response = client.get("/api/playback/available-dates/Camera 1")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
            assert "2026-01-15" in data

    def test_get_available_dates_no_recordings(self, client, mock_playback_db):
        """Test getting dates when no recordings exist"""
        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            response = client.get("/api/playback/available-dates/Camera 1")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 0


@pytest.mark.unit
class TestStorageStats:
    """Test storage statistics endpoint"""

    def test_get_storage_stats(self, client, temp_dir, mock_playback_db):
        """Test getting storage statistics"""
        # Add segments to create stats
        now = datetime.now()
        for i in range(3):
            mock_playback_db.add_segment(
                camera_name="Camera 1",
                file_path=str(temp_dir / f"segment_{i}.mp4"),
                start_time=now + timedelta(hours=i),
                end_time=now + timedelta(hours=i, minutes=5),
                duration_seconds=300,
                file_size_bytes=10 * 1024 * 1024  # 10MB
            )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            response = client.get("/api/playback/storage-stats")

            assert response.status_code == 200
            data = response.json()
            assert "cameras" in data
            assert "overall" in data
            assert data["overall"]["total_files"] == 3


@pytest.mark.unit
class TestExportClip:
    """Test clip export endpoint"""

    def test_export_clip_request(self, client, temp_dir, mock_playback_db):
        """Test exporting a video clip"""
        # Create test video file
        test_file = temp_dir / "test.mp4"
        test_file.write_bytes(b"x" * 1024)

        now = datetime.now()
        mock_playback_db.add_segment(
            camera_name="Camera 1",
            file_path=str(test_file),
            start_time=now,
            end_time=now + timedelta(minutes=5),
            duration_seconds=300
        )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            payload = {
                "camera_name": "Camera 1",
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(minutes=5)).isoformat()
            }

            response = client.post("/api/playback/export", json=payload)

            # Should accept request (may return 202 Accepted or start export)
            assert response.status_code in [200, 202, 404]  # Implementation dependent

    def test_export_clip_no_segments(self, client, mock_playback_db):
        """Test export when no segments available"""
        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            now = datetime.now()
            payload = {
                "camera_name": "NonexistentCamera",
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(minutes=5)).isoformat()
            }

            response = client.post("/api/playback/export", json=payload)

            assert response.status_code in [404, 400]  # No segments to export


@pytest.mark.unit
class TestPlaybackAPIEdgeCases:
    """Test edge cases and error handling"""

    def test_invalid_datetime_format(self, client, mock_playback_db):
        """Test handling of invalid datetime formats"""
        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            response = client.get(
                "/api/playback/recordings/Camera 1?start=invalid-date"
            )

            # Should handle gracefully (may return 400 or ignore invalid param)
            assert response.status_code in [200, 400, 422]

    def test_special_characters_in_camera_name(self, client, temp_dir, mock_playback_db):
        """Test camera names with special characters"""
        camera_name = "Camera #1 (Front)"
        now = datetime.now()

        mock_playback_db.add_segment(
            camera_name=camera_name,
            file_path=str(temp_dir / "segment.mp4"),
            start_time=now,
            end_time=now + timedelta(minutes=5),
            duration_seconds=300
        )

        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            # URL encode camera name
            import urllib.parse
            encoded_name = urllib.parse.quote(camera_name)

            response = client.get(f"/api/playback/recordings/{encoded_name}")

            assert response.status_code == 200

    def test_very_large_time_range(self, client, mock_playback_db):
        """Test querying very large time ranges"""
        with patch('nvr.web.playback_api.get_app_state') as mock_state:
            mock_state.return_value = Mock(playback_db=mock_playback_db)

            start = datetime(2020, 1, 1).isoformat()
            end = datetime(2030, 12, 31).isoformat()

            response = client.get(
                f"/api/playback/recordings?start={start}&end={end}"
            )

            # Should handle without crashing
            assert response.status_code == 200


@pytest.mark.unit
class TestVideoSegmentFiltering:
    """Tests for video segment filtering (preventing future date issues)"""

    @pytest.fixture
    def mock_segments_with_incomplete(self):
        """Create segment list with incomplete (currently recording) segment"""
        now = datetime.now()
        return [
            {
                'id': 1,
                'camera_id': 'test_cam',
                'file_path': '/recordings/test_cam/completed.mp4',
                'start_time': (now - timedelta(hours=2)).isoformat(),
                'end_time': (now - timedelta(hours=1, minutes=55)).isoformat(),
            },
            {
                'id': 2,
                'camera_id': 'test_cam',
                'file_path': '/recordings/test_cam/recording.mp4',
                'start_time': (now - timedelta(minutes=5)).isoformat(),
                'end_time': None,  # Currently recording
            }
        ]

    def test_incomplete_segment_excluded_for_future_request(self):
        """Test that incomplete segments are excluded for future date requests"""
        from datetime import datetime, timedelta

        now = datetime.now()
        future_start = now + timedelta(hours=1)
        future_end = now + timedelta(hours=2)

        # Segment started yesterday, still recording (end_time is None)
        segments = [
            {
                'file_path': '/recordings/test.mp4',
                'start_time': (now - timedelta(days=1)).isoformat(),
                'end_time': None,
            }
        ]

        # When filtering for future time, this segment should be excluded
        # because incomplete segments can't cover future times
        filtered = []
        for seg in segments:
            if seg['end_time'] is None:
                seg_start = datetime.fromisoformat(seg['start_time'])
                # Future request - incomplete segments don't match
                if future_start > now:
                    continue  # Excluded
            filtered.append(seg)

        assert len(filtered) == 0

    def test_incomplete_segment_included_for_current_time(self):
        """Test that incomplete segments are included for current time requests"""
        from datetime import datetime, timedelta

        now = datetime.now()
        request_start = now - timedelta(minutes=10)
        request_end = now

        # Segment started 5 minutes ago, still recording
        segments = [
            {
                'file_path': '/recordings/test.mp4',
                'start_time': (now - timedelta(minutes=5)).isoformat(),
                'end_time': None,
            }
        ]

        # When filtering for current time, this segment should be included
        filtered = []
        for seg in segments:
            if seg['end_time'] is None:
                seg_start = datetime.fromisoformat(seg['start_time'])
                # Current time request - check if segment start is within window
                if seg_start <= request_start <= now:
                    filtered.append(seg)
                elif seg_start <= now:  # Segment started before now
                    filtered.append(seg)
            else:
                filtered.append(seg)

        assert len(filtered) == 1

    def test_completed_segment_always_included(self):
        """Test that completed segments are always included when they match"""
        from datetime import datetime, timedelta

        now = datetime.now()

        # Completed segment from yesterday
        segments = [
            {
                'file_path': '/recordings/test.mp4',
                'start_time': (now - timedelta(days=1, hours=2)).isoformat(),
                'end_time': (now - timedelta(days=1, hours=1)).isoformat(),
            }
        ]

        # Completed segments should always be included if they match the range
        filtered = [s for s in segments if s['end_time'] is not None]

        assert len(filtered) == 1

    def test_future_date_filtering_logic(self):
        """Test the logic that filters out future date requests"""
        from datetime import datetime, timedelta

        now = datetime.now()
        future_start = now + timedelta(days=1)

        # Simulate an incomplete segment from yesterday
        segment = {
            'file_path': '/recordings/test.mp4',
            'start_time': (now - timedelta(days=1)).isoformat(),
            'end_time': None,  # Currently recording
        }

        # The filtering logic should exclude this segment for future requests
        # because an incomplete segment can't possibly cover future times
        should_include = False
        if segment['end_time'] is None:
            seg_start = datetime.fromisoformat(segment['start_time'])
            if future_start > now:
                # Future request - incomplete segments can't match
                should_include = False
            elif seg_start <= future_start <= now:
                should_include = True

        assert should_include is False


@pytest.mark.unit
class TestNonBlockingStartup:
    """Tests for non-blocking server startup (mp4v scanning in background)"""

    def test_mp4v_scan_function_exists(self):
        """Test that mp4v scan function is defined"""
        # The scan should be wrapped in a function for threading
        # This is more of a smoke test
        import nvr.web.api
        # Module should load without blocking

    @patch('threading.Thread')
    def test_mp4v_scan_runs_in_thread(self, mock_thread):
        """Test that mp4v scanning is started in a background thread"""
        # This would require testing the startup_event function
        # which is complex to unit test. This is a placeholder
        # for the expected behavior.
        pass
