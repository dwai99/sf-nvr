"""Integration tests for end-to-end recording pipeline"""

import pytest
import os
import time
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import cv2
import numpy as np

from nvr.core.recorder import RTSPRecorder
from nvr.core.playback_db import PlaybackDatabase
from nvr.core.storage_manager import StorageManager


@pytest.mark.integration
class TestRecordingPipeline:
    """Test complete recording pipeline from RTSP to storage"""

    @pytest.mark.asyncio
    async def test_recorder_creates_segments_in_database(self, temp_dir):
        """Test that recorder creates segments and stores them in database"""
        # Create database
        db_path = temp_dir / "test.db"
        playback_db = PlaybackDatabase(db_path)

        # Create recorder
        recorder = RTSPRecorder(
            camera_name="Test Camera",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            playback_db=playback_db,
            segment_duration=300
        )

        # Verify camera storage directory was created
        assert recorder.camera_storage.exists()

        # Verify database has no segments initially
        segments = playback_db.get_all_segments("Test Camera")
        assert len(segments) == 0

    @pytest.mark.asyncio
    async def test_storage_manager_cleans_old_recordings(self, temp_dir):
        """Test that storage manager removes old recordings from disk and database"""
        # Create database
        db_path = temp_dir / "test.db"
        playback_db = PlaybackDatabase(db_path)

        # Create storage manager
        storage_manager = StorageManager(
            storage_path=temp_dir,
            retention_days=7,
            cleanup_threshold_percent=50,
            target_percent=40,
            playback_db=playback_db
        )

        # Create camera directory
        camera_dir = temp_dir / "test_camera"
        camera_dir.mkdir(parents=True, exist_ok=True)

        # Create old file (15 days old)
        old_file = camera_dir / "old_segment.mp4"
        old_file.write_bytes(b"x" * (10 * 1024 * 1024))  # 10 MB
        # Set file mtime to 15 days ago so cleanup considers it old
        old_timestamp = time.time() - (15 * 24 * 3600)
        os.utime(old_file, (old_timestamp, old_timestamp))

        # Add to database
        old_time = datetime.now() - timedelta(days=15)
        playback_db.add_segment(
            camera_id="test_camera",
            file_path=str(old_file),
            start_time=old_time,
            end_time=old_time + timedelta(minutes=5),
            duration_seconds=300,
            file_size_bytes=10 * 1024 * 1024
        )

        # Verify file exists and is in database
        assert old_file.exists()
        segments_before = playback_db.get_all_segments("test_camera")
        assert len(segments_before) == 1

        # Mock disk usage to trigger cleanup
        with patch('psutil.disk_usage') as mock_disk:
            mock_disk.return_value = type('obj', (object,), {
                'total': 100 * 1024**3,
                'used': 90 * 1024**3,
                'free': 10 * 1024**3,
                'percent': 90.0
            })()

            # Run cleanup
            stats = storage_manager.check_and_cleanup()

        # Verify cleanup was triggered
        assert stats['cleanup_triggered'] is True
        assert stats['files_deleted'] >= 1

        # Verify file was deleted
        assert not old_file.exists()

        # Verify database was updated
        segments_after = playback_db.get_all_segments("test_camera")
        assert len(segments_after) == 0


@pytest.mark.integration
class TestCameraLifecycle:
    """Test camera add/remove/rename lifecycle"""

    def test_camera_directory_creation(self, temp_dir):
        """Test that camera directories are created correctly"""
        # Create database
        db_path = temp_dir / "test.db"
        playback_db = PlaybackDatabase(db_path)

        # Create recorder with camera_id
        recorder = RTSPRecorder(
            camera_name="Front Door",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            camera_id="cam_001",
            playback_db=playback_db
        )

        # Verify directory created with camera_id
        expected_dir = temp_dir / "cam_001"
        assert expected_dir.exists()
        assert recorder.camera_storage == expected_dir

    def test_camera_rename_preserves_recordings(self, temp_dir):
        """Test that renaming camera preserves recordings via camera_id"""
        # Create database
        db_path = temp_dir / "test.db"
        playback_db = PlaybackDatabase(db_path)

        # Create recorder with camera_id
        recorder1 = RTSPRecorder(
            camera_name="Front Door",
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            camera_id="cam_001",
            playback_db=playback_db
        )

        # Create a file in the camera storage
        test_file = recorder1.camera_storage / "test.mp4"
        test_file.write_bytes(b"test data")

        # Add segment to database with camera_id
        playback_db.add_segment(
            camera_id="cam_001",
            file_path=str(test_file),
            start_time=datetime.now(),
            camera_name="Front Door",
            end_time=datetime.now() + timedelta(minutes=5),
            duration_seconds=300
        )

        # "Rename" camera by creating new recorder with same camera_id
        recorder2 = RTSPRecorder(
            camera_name="Main Entrance",  # New name
            rtsp_url="rtsp://example.com/stream",
            storage_path=temp_dir,
            camera_id="cam_001",  # Same ID
            playback_db=playback_db
        )

        # Verify same storage directory is used
        assert recorder2.camera_storage == recorder1.camera_storage

        # Verify file still exists
        assert test_file.exists()

    def test_multiple_cameras_independent_storage(self, temp_dir):
        """Test that multiple cameras have independent storage"""
        # Create database
        db_path = temp_dir / "test.db"
        playback_db = PlaybackDatabase(db_path)

        # Create multiple recorders
        recorder1 = RTSPRecorder(
            camera_name="Camera 1",
            rtsp_url="rtsp://example.com/stream1",
            storage_path=temp_dir,
            camera_id="cam_001",
            playback_db=playback_db
        )

        recorder2 = RTSPRecorder(
            camera_name="Camera 2",
            rtsp_url="rtsp://example.com/stream2",
            storage_path=temp_dir,
            camera_id="cam_002",
            playback_db=playback_db
        )

        recorder3 = RTSPRecorder(
            camera_name="Camera 3",
            rtsp_url="rtsp://example.com/stream3",
            storage_path=temp_dir,
            camera_id="cam_003",
            playback_db=playback_db
        )

        # Verify each has independent storage
        assert recorder1.camera_storage != recorder2.camera_storage
        assert recorder2.camera_storage != recorder3.camera_storage
        assert recorder1.camera_storage != recorder3.camera_storage

        # Verify all directories exist
        assert recorder1.camera_storage.exists()
        assert recorder2.camera_storage.exists()
        assert recorder3.camera_storage.exists()


@pytest.mark.integration
class TestDatabaseStorageSync:
    """Test synchronization between database and storage"""

    def test_cleanup_removes_orphaned_database_entries(self, temp_dir):
        """Test that cleanup removes database entries for missing files"""
        # Create database
        db_path = temp_dir / "test.db"
        playback_db = PlaybackDatabase(db_path)

        # Add segments for files that don't exist
        camera_dir = temp_dir / "test_camera"
        camera_dir.mkdir(parents=True)

        for i in range(5):
            playback_db.add_segment(
                camera_id="test_camera",
                file_path=str(camera_dir / f"missing_{i}.mp4"),
                start_time=datetime.now() - timedelta(hours=i),
                end_time=datetime.now() - timedelta(hours=i) + timedelta(minutes=5),
                duration_seconds=300
            )

        # Verify segments exist in database
        segments_before = playback_db.get_all_segments("test_camera")
        assert len(segments_before) == 5

        # Run cleanup to remove orphaned entries
        deleted = playback_db.cleanup_deleted_files(temp_dir)

        # All should be deleted since files don't exist
        assert deleted == 5

        # Verify database is cleaned
        segments_after = playback_db.get_all_segments("test_camera")
        assert len(segments_after) == 0

    def test_storage_cleanup_updates_database(self, temp_dir):
        """Test that storage cleanup also updates database"""
        # Create database
        db_path = temp_dir / "test.db"
        playback_db = PlaybackDatabase(db_path)

        # Create storage manager
        storage_manager = StorageManager(
            storage_path=temp_dir,
            retention_days=7,
            cleanup_threshold_percent=50,
            target_percent=40,
            playback_db=playback_db
        )

        # Create camera directory with old files
        camera_dir = temp_dir / "test_camera"
        camera_dir.mkdir(parents=True)

        files = []
        for i in range(3):
            file_path = camera_dir / f"old_{i}.mp4"
            file_path.write_bytes(b"x" * (5 * 1024 * 1024))  # 5 MB
            # Set file mtime to 10 days ago so cleanup considers it old
            old_timestamp = time.time() - (10 * 24 * 3600)
            os.utime(file_path, (old_timestamp, old_timestamp))
            files.append(file_path)

            # Add to database
            old_time = datetime.now() - timedelta(days=10)
            playback_db.add_segment(
                camera_id="test_camera",
                file_path=str(file_path),
                start_time=old_time + timedelta(hours=i),
                end_time=old_time + timedelta(hours=i, minutes=5),
                duration_seconds=300,
                file_size_bytes=5 * 1024 * 1024
            )

        # Verify files and database entries exist
        for f in files:
            assert f.exists()

        segments_before = playback_db.get_all_segments("test_camera")
        assert len(segments_before) == 3

        # Mock disk usage to trigger cleanup
        with patch('psutil.disk_usage') as mock_disk:
            mock_disk.return_value = type('obj', (object,), {
                'total': 100 * 1024**3,
                'used': 90 * 1024**3,
                'free': 10 * 1024**3,
                'percent': 90.0
            })()

            # Run cleanup
            stats = storage_manager.check_and_cleanup()

        # Verify cleanup was triggered and files deleted
        assert stats['cleanup_triggered'] is True
        assert stats['files_deleted'] >= 1

        # Verify database was synchronized
        segments_after = playback_db.get_all_segments("test_camera")
        assert len(segments_after) < len(segments_before)


@pytest.mark.integration
class TestMultiCameraWorkflow:
    """Test multi-camera recording workflows"""

    def test_multiple_cameras_record_independently(self, temp_dir):
        """Test that multiple cameras can record independently"""
        # Create database
        db_path = temp_dir / "test.db"
        playback_db = PlaybackDatabase(db_path)

        # Create multiple recorders
        recorders = []
        for i in range(3):
            recorder = RTSPRecorder(
                camera_name=f"Camera {i+1}",
                rtsp_url=f"rtsp://example.com/stream{i+1}",
                storage_path=temp_dir,
                camera_id=f"cam_{i+1:03d}",
                playback_db=playback_db
            )
            recorders.append(recorder)

        # Verify each recorder has independent storage
        for i, recorder in enumerate(recorders):
            assert recorder.camera_storage == temp_dir / f"cam_{i+1:03d}"
            assert recorder.camera_storage.exists()

        # Verify storage directories are separate
        storage_dirs = [r.camera_storage for r in recorders]
        assert len(set(storage_dirs)) == 3  # All unique

    def test_query_recordings_across_cameras(self, temp_dir):
        """Test querying recordings across multiple cameras"""
        # Create database
        db_path = temp_dir / "test.db"
        playback_db = PlaybackDatabase(db_path)

        # Add segments for multiple cameras
        base_time = datetime(2026, 1, 20, 12, 0, 0)

        for camera_num in range(1, 4):
            for segment_num in range(5):
                start_time = base_time + timedelta(minutes=segment_num * 10)
                playback_db.add_segment(
                    camera_id=f"Camera {camera_num}",
                    file_path=f"/recordings/cam_{camera_num:03d}/segment_{segment_num}.mp4",
                    start_time=start_time,
                    end_time=start_time + timedelta(minutes=5),
                    duration_seconds=300,
                    file_size_bytes=10 * 1024 * 1024
                )

        # Query all cameras for time range
        all_segments = playback_db.get_all_segments_in_range(
            start_time=base_time,
            end_time=base_time + timedelta(hours=1)
        )

        # Should have data for 3 cameras
        assert len(all_segments) == 3
        assert "Camera 1" in all_segments
        assert "Camera 2" in all_segments
        assert "Camera 3" in all_segments

        # Each camera should have 5 segments
        for camera_segments in all_segments.values():
            assert len(camera_segments) == 5


@pytest.mark.integration
class TestStorageQuotaManagement:
    """Test storage quota and cleanup management"""

    def test_cleanup_respects_retention_and_quota(self, temp_dir):
        """Test that cleanup respects both retention policy and disk quota"""
        # Create database
        db_path = temp_dir / "test.db"
        playback_db = PlaybackDatabase(db_path)

        # Create storage manager with 7-day retention
        storage_manager = StorageManager(
            storage_path=temp_dir,
            retention_days=7,
            cleanup_threshold_percent=50,
            target_percent=40,
            playback_db=playback_db
        )

        # Create camera directory
        camera_dir = temp_dir / "test_camera"
        camera_dir.mkdir(parents=True)

        # Create old files (beyond retention)
        old_files = []
        for i in range(3):
            file_path = camera_dir / f"old_{i}.mp4"
            file_path.write_bytes(b"x" * (5 * 1024 * 1024))  # 5 MB
            # Set file mtime to 10 days ago so cleanup considers it old
            old_timestamp = time.time() - (10 * 24 * 3600)
            os.utime(file_path, (old_timestamp, old_timestamp))
            old_files.append(file_path)

            old_time = datetime.now() - timedelta(days=10)
            playback_db.add_segment(
                camera_id="test_camera",
                file_path=str(file_path),
                start_time=old_time + timedelta(hours=i),
                end_time=old_time + timedelta(hours=i, minutes=5),
                duration_seconds=300,
                file_size_bytes=5 * 1024 * 1024
            )

        # Create recent files (within retention)
        recent_files = []
        for i in range(3):
            file_path = camera_dir / f"recent_{i}.mp4"
            file_path.write_bytes(b"x" * (5 * 1024 * 1024))  # 5 MB
            recent_files.append(file_path)

            recent_time = datetime.now() - timedelta(days=3)
            playback_db.add_segment(
                camera_id="test_camera",
                file_path=str(file_path),
                start_time=recent_time + timedelta(hours=i),
                end_time=recent_time + timedelta(hours=i, minutes=5),
                duration_seconds=300,
                file_size_bytes=5 * 1024 * 1024
            )

        # Mock high disk usage
        with patch('psutil.disk_usage') as mock_disk:
            mock_disk.return_value = type('obj', (object,), {
                'total': 100 * 1024**3,
                'used': 85 * 1024**3,
                'free': 15 * 1024**3,
                'percent': 85.0
            })()

            # Run cleanup
            stats = storage_manager.check_and_cleanup()

        # Verify old files were deleted
        for f in old_files:
            assert not f.exists()

        # Verify recent files were preserved
        for f in recent_files:
            assert f.exists()
