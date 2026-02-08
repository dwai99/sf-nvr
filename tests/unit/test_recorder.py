"""Unit tests for RTSPRecorder - RTSP stream recording and management"""

import pytest
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import queue
import threading
import time

from nvr.core.recorder import RTSPRecorder, RecorderManager


@pytest.mark.unit
class TestRTSPRecorderInit:
    """Test RTSPRecorder initialization"""

    def test_init_basic(self, temp_dir):
        """Test basic recorder initialization"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        assert recorder.camera_name == "Test Camera"
        assert recorder.rtsp_url == "rtsp://example.com/stream"
        assert recorder.storage_path == temp_dir
        assert recorder.segment_duration == 300  # Default 5 minutes
        assert recorder.codec == 'h264'
        assert recorder.container == 'mp4'
        assert recorder.is_recording is False

    def test_init_with_custom_params(self, temp_dir):
        """Test recorder initialization with custom parameters"""
        recorder = RTSPRecorder(
            camera_name="Custom Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            segment_duration=600,
            codec='h265',
            container='mkv'
        )

        assert recorder.segment_duration == 600
        assert recorder.codec == 'h265'
        assert recorder.container == 'mkv'

    def test_init_creates_storage_directory(self, temp_dir):
        """Test that camera storage directory is created"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # Should create directory using camera_id
        assert recorder.camera_storage.exists()
        assert recorder.camera_storage.is_dir()

    def test_sanitize_name(self, temp_dir):
        """Test camera name sanitization for filesystem"""
        recorder = RTSPRecorder(
            camera_name="Test/Camera:123*",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # Special characters should be replaced with underscores
        sanitized = recorder._sanitize_name("Test/Camera:123*")
        assert "/" not in sanitized
        assert ":" not in sanitized
        assert "*" not in sanitized
        assert sanitized == "Test_Camera_123_"

    def test_camera_id_fallback(self, temp_dir):
        """Test camera_id falls back to sanitized name if not provided"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # Should use sanitized name as camera_id
        assert recorder.camera_id == recorder._sanitize_name("Test Camera")

    def test_camera_id_explicit(self, temp_dir):
        """Test explicit camera_id is used when provided"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            camera_id="cam_001"
        )

        assert recorder.camera_id == "cam_001"
        assert recorder.camera_storage == temp_dir / "cam_001"


@pytest.mark.unit
class TestRTSPRecorderControl:
    """Test recorder start/stop control"""

    @pytest.mark.asyncio
    async def test_start_recording(self, temp_dir):
        """Test starting recording"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        with patch('threading.Thread') as mock_thread:
            result = await recorder.start()

            assert result is True
            assert recorder.is_recording is True
            mock_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_recording_already_running(self, temp_dir):
        """Test starting recording when already running"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        recorder.is_recording = True

        result = await recorder.start()

        # Should return False when already running
        assert result is False

    def test_stop_recording(self, temp_dir):
        """Test stopping recording"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        recorder.is_recording = True
        mock_thread = Mock()
        mock_thread.is_alive.return_value = False
        recorder.record_thread = mock_thread

        recorder.stop()

        assert recorder.is_recording is False

    def test_stop_recording_waits_for_thread(self, temp_dir):
        """Test that stop waits for recording thread"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        recorder.record_thread = mock_thread
        recorder.is_recording = True

        recorder.stop()

        # Should call join with timeout
        mock_thread.join.assert_called_once_with(timeout=0.5)


@pytest.mark.unit
class TestRTSPRecorderSegments:
    """Test recording segment management"""

    def test_get_next_segment_boundary(self, temp_dir):
        """Test calculation of next segment boundary"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            segment_duration=300  # 5 minutes
        )

        # Call method and check result
        boundary = recorder._get_next_segment_boundary()

        # Should align to 5-minute boundary
        assert boundary.minute % 5 == 0
        assert boundary.second == 0
        assert boundary.microsecond == 0
        # Should be in the future
        assert boundary > datetime.now()

    def test_start_new_segment_creates_writer(self, temp_dir):
        """Test that starting new segment creates video writer"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # Mock VideoWriter
        with patch('cv2.VideoWriter') as mock_writer_class:
            mock_writer = Mock()
            mock_writer.isOpened.return_value = True
            mock_writer_class.return_value = mock_writer

            recorder._start_new_segment(fps=30, width=1920, height=1080)

            # Should create writer
            mock_writer_class.assert_called_once()
            assert recorder.writer == mock_writer
            assert recorder.current_segment_start is not None
            assert recorder.current_segment_path is not None

    def test_start_new_segment_closes_previous(self, temp_dir, playback_db):
        """Test that starting new segment closes previous writer"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            playback_db=playback_db
        )

        # Create mock previous writer and actual file
        old_writer = Mock()
        old_writer.isOpened.return_value = True
        recorder.writer = old_writer
        recorder.current_segment_start = datetime.now() - timedelta(minutes=5)
        old_segment = recorder.camera_storage / "old_segment.mp4"
        old_segment.write_bytes(b"test data")
        recorder.current_segment_path = old_segment

        # Mock new writer
        with patch('cv2.VideoWriter') as mock_writer_class:
            mock_writer = Mock()
            mock_writer.isOpened.return_value = True
            mock_writer_class.return_value = mock_writer

            recorder._start_new_segment(fps=30, width=1920, height=1080)

            # Should release old writer
            old_writer.release.assert_called_once()

    def test_get_fourcc_h264(self, temp_dir):
        """Test FOURCC code generation for H.264"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            codec='h264'
        )

        fourcc = recorder._get_fourcc()
        assert fourcc == 'H264'

    def test_get_fourcc_h265(self, temp_dir):
        """Test FOURCC code generation for H.265"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            codec='h265'
        )

        fourcc = recorder._get_fourcc()
        assert fourcc == 'HEVC'


@pytest.mark.unit
class TestRTSPRecorderFrames:
    """Test frame capture and storage"""

    def test_get_latest_frame_empty_queue(self, temp_dir):
        """Test getting frame when queue is empty"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # No frames in queue
        frame = recorder.get_latest_frame()

        # Should return None when no frames available
        assert frame is None

    def test_get_latest_frame_from_queue(self, temp_dir):
        """Test getting frame from queue"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # Add mock frame to queue
        test_frame = b"fake_jpeg_data"
        recorder.frame_queue.put(test_frame)

        frame = recorder.get_latest_frame()

        assert frame == test_frame

    def test_get_latest_frame_uses_cache(self, temp_dir):
        """Test that latest frame is cached"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # Add frame and retrieve it
        test_frame = b"cached_frame"
        recorder.frame_queue.put(test_frame)
        recorder.get_latest_frame()

        # Queue is now empty, but cached frame should be available
        assert recorder.last_frame == test_frame

        # Getting frame again should return cached frame
        frame = recorder.get_latest_frame()
        assert frame == test_frame


@pytest.mark.unit
class TestRTSPRecorderMotion:
    """Test motion event tracking"""

    def test_log_motion_event_starts_tracking(self, temp_dir, playback_db):
        """Test that motion event starts motion tracking"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            playback_db=playback_db
        )

        # No motion event initially
        assert recorder.motion_event_start is None
        assert recorder.motion_frame_count == 0

        # Log motion event
        recorder.log_motion_event(intensity=75.0)

        # Should start tracking motion
        assert recorder.motion_event_start is not None
        assert recorder.motion_frame_count == 1

    def test_log_motion_event_continues_tracking(self, temp_dir, playback_db):
        """Test that subsequent motion events continue tracking"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            playback_db=playback_db
        )

        # Start motion event
        recorder.log_motion_event(intensity=75.0)
        first_start = recorder.motion_event_start

        # Log another motion event
        time.sleep(0.01)
        recorder.log_motion_event(intensity=80.0)

        # Should keep same start time but increment frame count
        assert recorder.motion_event_start == first_start
        assert recorder.motion_frame_count == 2

    def test_end_motion_event_resets_tracking(self, temp_dir, playback_db):
        """Test that ending motion event resets tracking"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            playback_db=playback_db
        )

        # Start motion event
        recorder.log_motion_event(intensity=75.0)
        assert recorder.motion_event_start is not None

        # End motion event
        recorder.end_motion_event()

        # Should reset tracking
        assert recorder.motion_event_start is None
        assert recorder.motion_frame_count == 0

    def test_log_motion_event_without_database(self, temp_dir):
        """Test motion event without database (should not track)"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            playback_db=None  # No database
        )

        # Log motion event (should do nothing)
        recorder.log_motion_event(intensity=75.0)

        # Should not start tracking without database
        assert recorder.motion_event_start is None
        assert recorder.motion_frame_count == 0


@pytest.mark.unit
class TestRTSPRecorderCleanup:
    """Test resource cleanup"""

    def test_cleanup_releases_capture(self, temp_dir):
        """Test that cleanup releases video capture"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # Create mock capture
        mock_capture = Mock()
        recorder.capture = mock_capture

        recorder._cleanup()

        # Should release capture
        mock_capture.release.assert_called_once()
        assert recorder.capture is None

    def test_cleanup_releases_writer(self, temp_dir):
        """Test that cleanup releases video writer"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # Create mock writer
        mock_writer = Mock()
        mock_writer.isOpened.return_value = True
        recorder.writer = mock_writer
        recorder.current_segment_start = datetime.now()

        recorder._cleanup()

        # Should release writer
        mock_writer.release.assert_called_once()
        assert recorder.writer is None

    def test_cleanup_handles_none_values(self, temp_dir):
        """Test that cleanup handles None values gracefully"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # Ensure capture and writer are None
        recorder.capture = None
        recorder.writer = None

        # Should not crash
        recorder._cleanup()

        assert recorder.capture is None
        assert recorder.writer is None


@pytest.mark.unit
class TestRTSPRecorderHealth:
    """Test recorder health tracking"""

    def test_health_tracks_connection_attempts(self, temp_dir):
        """Test that connection attempts are tracked"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        assert recorder.last_connection_attempt is None
        assert recorder.last_successful_connection is None
        assert recorder.total_reconnects == 0

    def test_health_tracks_stream_properties(self, temp_dir):
        """Test that stream properties are tracked"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        assert recorder.stream_fps == 0.0
        assert recorder.stream_width == 0
        assert recorder.stream_height == 0

    def test_consecutive_failures_tracking(self, temp_dir):
        """Test that consecutive failures are tracked"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        assert recorder.consecutive_failures == 0


@pytest.mark.unit
class TestRecorderManager:
    """Test RecorderManager class"""

    def test_init_manager(self, temp_dir):
        """Test manager initialization"""
        manager = RecorderManager(
            storage_path=temp_dir,
            segment_duration=300
        )

        assert manager.storage_path == temp_dir
        assert manager.segment_duration == 300
        assert len(manager.recorders) == 0

    def test_add_recorder(self, temp_dir):
        """Test adding recorder to manager"""
        manager = RecorderManager(storage_path=temp_dir)

        # Add recorder
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )
        manager.recorders["test_camera"] = recorder

        assert len(manager.recorders) == 1
        assert "test_camera" in manager.recorders

    def test_get_recorder(self, temp_dir):
        """Test getting recorder from manager"""
        manager = RecorderManager(storage_path=temp_dir)

        # Add recorder
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )
        manager.recorders["test_camera"] = recorder

        # Get recorder
        retrieved = manager.get_recorder("test_camera")

        assert retrieved is recorder

    def test_get_recorder_nonexistent(self, temp_dir):
        """Test getting nonexistent recorder returns None"""
        manager = RecorderManager(storage_path=temp_dir)

        result = manager.get_recorder("nonexistent")

        assert result is None

    def test_stop_all_recorders(self, temp_dir):
        """Test stopping all recorders"""
        manager = RecorderManager(storage_path=temp_dir)

        # Add multiple recorders
        recorder1 = RTSPRecorder(
            camera_name="Camera 1",
            rtsp_url="rtsp://example.com/stream1",
            storage_path=temp_dir
        )
        recorder2 = RTSPRecorder(
            camera_name="Camera 2",
            rtsp_url="rtsp://example.com/stream2",
            storage_path=temp_dir
        )

        # Mock stop methods
        recorder1.stop = Mock()
        recorder2.stop = Mock()

        manager.recorders["camera1"] = recorder1
        manager.recorders["camera2"] = recorder2

        # Stop all
        manager.stop_all()

        # Should call stop on both recorders
        recorder1.stop.assert_called_once()
        recorder2.stop.assert_called_once()


@pytest.mark.unit
class TestRTSPRecorderEdgeCases:
    """Test edge cases and error conditions"""

    def test_sanitize_name_with_spaces(self, temp_dir):
        """Test name sanitization preserves spaces"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        sanitized = recorder._sanitize_name("Test Camera")
        assert sanitized == "Test Camera"

    def test_sanitize_name_with_unicode(self, temp_dir):
        """Test name sanitization handles unicode"""
        recorder = RTSPRecorder(
            camera_name="Test",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        sanitized = recorder._sanitize_name("Caméra Tést")
        # Check that sanitization works (may keep or replace unicode depending on implementation)
        assert isinstance(sanitized, str)
        assert len(sanitized) > 0

    def test_frame_queue_maxsize(self, temp_dir):
        """Test that frame queue has maxsize of 2"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        # Queue should have maxsize of 2
        assert recorder.frame_queue.maxsize == 2

    def test_sleep_if_recording_stops_early(self, temp_dir):
        """Test that sleep stops early when recording stops"""
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir
        )

        recorder.is_recording = True

        # Start sleep in background
        def stop_recording():
            time.sleep(0.1)
            recorder.is_recording = False

        threading.Thread(target=stop_recording, daemon=True).start()

        # Should return early when is_recording becomes False
        start = time.time()
        recorder._sleep_if_recording(10)
        elapsed = time.time() - start

        # Should finish in ~0.1s, not 10s
        assert elapsed < 1.0
