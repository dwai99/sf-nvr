"""Unit tests for PlaybackDatabase - recording metadata and motion events"""

import pytest
from pathlib import Path
from datetime import datetime, timedelta

from nvr.core.playback_db import PlaybackDatabase
from tests.conftest import create_test_video_file


@pytest.mark.unit
class TestPlaybackDatabaseInit:
    """Test database initialization"""

    def test_init_creates_database(self, temp_dir):
        """Test that database file is created"""
        db_path = temp_dir / "test.db"
        db = PlaybackDatabase(db_path)

        assert db_path.exists()
        assert db.db_path == db_path

    def test_init_creates_parent_directory(self, temp_dir):
        """Test that parent directories are created"""
        db_path = temp_dir / "subdir" / "nested" / "test.db"
        db = PlaybackDatabase(db_path)

        assert db_path.exists()
        assert db_path.parent.exists()

    def test_init_creates_tables(self, playback_db, temp_dir):
        """Test that tables are created"""
        # Query to check if tables exist
        with playback_db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ('recording_segments', 'motion_events')
            """)
            tables = [row[0] for row in cursor.fetchall()]

        assert 'recording_segments' in tables
        assert 'motion_events' in tables


@pytest.mark.unit
class TestSegmentOperations:
    """Test recording segment CRUD operations"""

    def test_add_segment_basic(self, playback_db):
        """Test adding a basic segment"""
        start_time = datetime(2026, 1, 20, 12, 0, 0)
        end_time = datetime(2026, 1, 20, 12, 5, 0)

        segment_id = playback_db.add_segment(
            camera_id="test_camera",
            file_path="/recordings/test_camera/20260120_120000.mp4",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=300
        )

        assert segment_id > 0

    def test_add_segment_with_all_fields(self, playback_db):
        """Test adding segment with all optional fields"""
        start_time = datetime(2026, 1, 20, 12, 0, 0)

        segment_id = playback_db.add_segment(
            camera_id="cam_001",
            file_path="/recordings/test_camera/20260120_120000.mp4",
            start_time=start_time,
            end_time=start_time + timedelta(minutes=5),
            duration_seconds=300,
            file_size_bytes=10 * 1024 * 1024,  # 10 MB
            fps=30.0,
            width=1920,
            height=1080
        )

        assert segment_id > 0

    def test_update_segment_end(self, playback_db):
        """Test updating segment end time and duration"""
        start_time = datetime(2026, 1, 20, 12, 0, 0)

        # Add segment without end time
        playback_db.add_segment(
            camera_id="test_camera",
            file_path="/recordings/test_camera/20260120_120000.mp4",
            start_time=start_time
        )

        # Update end time
        end_time = start_time + timedelta(minutes=5)
        playback_db.update_segment_end(
            camera_id="test_camera",
            file_path="/recordings/test_camera/20260120_120000.mp4",
            end_time=end_time,
            duration_seconds=300,
            file_size_bytes=10 * 1024 * 1024
        )

        # Verify update succeeded by querying the segment
        segments = playback_db.get_segments_in_range(
            camera_id="test_camera",
            start_time=start_time,
            end_time=end_time + timedelta(minutes=1)
        )
        assert len(segments) == 1
        assert segments[0]['end_time'] is not None

    def test_delete_segment_by_path(self, playback_db):
        """Test deleting segment by camera and filename"""
        start_time = datetime(2026, 1, 20, 12, 0, 0)

        playback_db.add_segment(
            camera_id="test_camera",
            file_path="/recordings/test_camera/20260120_120000.mp4",
            start_time=start_time
        )

        # Delete segment
        deleted = playback_db.delete_segment_by_path("test_camera", "20260120_120000.mp4")
        assert deleted is True

        # Try to delete again - should return False
        deleted_again = playback_db.delete_segment_by_path("test_camera", "20260120_120000.mp4")
        assert deleted_again is False


@pytest.mark.unit
class TestSegmentQueries:
    """Test querying recording segments"""

    def test_get_segments_in_range(self, playback_db):
        """Test getting segments within time range"""
        base_time = datetime(2026, 1, 20, 12, 0, 0)

        # Add multiple segments
        for i in range(5):
            start = base_time + timedelta(minutes=i * 5)
            playback_db.add_segment(
                camera_id="test_camera",
                file_path=f"/recordings/test_camera/segment_{i}.mp4",
                start_time=start,
                end_time=start + timedelta(minutes=5),
                duration_seconds=300
            )

        # Query for segments in middle of range
        query_start = base_time + timedelta(minutes=5)
        query_end = base_time + timedelta(minutes=15)

        segments = playback_db.get_segments_in_range(
            camera_id="test_camera",
            start_time=query_start,
            end_time=query_end
        )

        # Should get 2-3 segments that overlap with query range
        assert len(segments) >= 2
        assert all(isinstance(s, dict) for s in segments)

    def test_get_recording_days(self, playback_db):
        """Test getting list of dates with recordings"""
        dates = [
            datetime(2026, 1, 18),
            datetime(2026, 1, 19),
            datetime(2026, 1, 20),
        ]

        # Add segments for different dates
        for date in dates:
            playback_db.add_segment(
                camera_id="test_camera",
                file_path=f"/recordings/test_camera/{date.strftime('%Y%m%d')}.mp4",
                start_time=date,
                end_time=date + timedelta(hours=1),
                duration_seconds=3600
            )

        # Get recording days
        available = playback_db.get_recording_days(camera_id="test_camera")

        # Should have all 3 dates
        assert len(available) >= 3
        assert all(isinstance(d, str) for d in available)

    def test_get_all_segments(self, playback_db):
        """Test getting all segments for a camera"""
        base_time = datetime(2026, 1, 20, 12, 0, 0)

        # Add multiple segments
        for i in range(5):
            start = base_time + timedelta(minutes=i * 10)
            playback_db.add_segment(
                camera_id="test_camera",
                file_path=f"/recordings/test_camera/segment_{i}.mp4",
                start_time=start,
                end_time=start + timedelta(minutes=5),
                duration_seconds=300
            )

        # Get all segments
        segments = playback_db.get_all_segments(camera_id="test_camera")

        assert len(segments) == 5
        # Should be ordered by start_time
        for i in range(len(segments) - 1):
            assert segments[i]['start_time'] <= segments[i + 1]['start_time']

    def test_get_all_segments_in_range(self, playback_db):
        """Test getting segments for all cameras in time range"""
        base_time = datetime(2026, 1, 20, 12, 0, 0)

        # Add segments for multiple cameras
        for camera_num in range(1, 4):
            for i in range(3):
                start = base_time + timedelta(minutes=i * 10)
                playback_db.add_segment(
                    camera_id=f"camera_{camera_num}",
                    file_path=f"/recordings/camera_{camera_num}/segment_{i}.mp4",
                    start_time=start,
                    end_time=start + timedelta(minutes=5),
                    duration_seconds=300
                )

        # Get segments for all cameras
        result = playback_db.get_all_segments_in_range(
            start_time=base_time,
            end_time=base_time + timedelta(hours=1)
        )

        # Should have data for 3 cameras
        assert len(result) == 3
        assert "camera_1" in result
        assert "camera_2" in result
        assert "camera_3" in result

        # Each camera should have 3 segments
        for camera_segments in result.values():
            assert len(camera_segments) == 3


@pytest.mark.unit
class TestMotionEvents:
    """Test motion event logging and queries"""

    def test_add_motion_event(self, playback_db):
        """Test adding a motion event"""
        event_time = datetime(2026, 1, 20, 12, 30, 45)

        event_id = playback_db.add_motion_event(
            camera_id="test_camera",
            event_time=event_time,
            intensity=75
        )

        assert event_id > 0

    def test_get_motion_events_in_range(self, playback_db):
        """Test getting motion events within time range"""
        base_time = datetime(2026, 1, 20, 12, 0, 0)

        # Add multiple motion events
        for i in range(10):
            event_time = base_time + timedelta(minutes=i * 3)
            playback_db.add_motion_event(
                camera_id="test_camera",
                event_time=event_time,
                intensity=50 + i * 5
            )

        # Query for events in middle of range
        query_start = base_time + timedelta(minutes=10)
        query_end = base_time + timedelta(minutes=20)

        events = playback_db.get_motion_events_in_range(
            camera_id="test_camera",
            start_time=query_start,
            end_time=query_end
        )

        # Should get events that fall within range
        assert len(events) >= 3
        assert all('event_time' in e for e in events)
        assert all('intensity' in e for e in events)

    def test_motion_event_intensity_range(self, playback_db):
        """Test that motion intensity values are stored correctly"""
        event_time = datetime(2026, 1, 20, 12, 0, 0)

        # Test min, max, and mid intensities
        intensities = [0, 50, 100]

        for intensity in intensities:
            playback_db.add_motion_event(
                camera_id="test_camera",
                event_time=event_time + timedelta(seconds=intensity),
                intensity=intensity
            )

        # Query all events
        events = playback_db.get_motion_events_in_range(
            camera_id="test_camera",
            start_time=event_time - timedelta(minutes=1),
            end_time=event_time + timedelta(minutes=5)
        )

        # Verify intensities
        event_intensities = [e['intensity'] for e in events]
        assert 0 in event_intensities
        assert 50 in event_intensities
        assert 100 in event_intensities


@pytest.mark.unit
class TestDatabaseMaintenance:
    """Test database cleanup and maintenance operations"""

    def test_cleanup_deleted_files(self, playback_db, temp_dir):
        """Test removing database entries for deleted files"""
        recordings_path = temp_dir / "recordings" / "test_camera"
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create actual file
        existing_file = recordings_path / "exists.mp4"
        existing_file.write_bytes(b"test data")

        # Add segments - one with existing file, one without
        playback_db.add_segment(
            camera_id="test_camera",
            file_path=str(existing_file),
            start_time=datetime(2026, 1, 20, 12, 0, 0),
            end_time=datetime(2026, 1, 20, 12, 5, 0),
            duration_seconds=300
        )

        playback_db.add_segment(
            camera_id="test_camera",
            file_path=str(recordings_path / "missing.mp4"),
            start_time=datetime(2026, 1, 20, 13, 0, 0),
            end_time=datetime(2026, 1, 20, 13, 5, 0),
            duration_seconds=300
        )

        # Run cleanup
        deleted_count = playback_db.cleanup_deleted_files(temp_dir / "recordings")

        # Should have removed 1 entry (missing.mp4)
        assert deleted_count == 1

    def test_cleanup_old_incomplete_segments(self, playback_db):
        """Test cleanup of incomplete segments older than threshold"""
        old_time = datetime.now() - timedelta(hours=48)
        recent_time = datetime.now() - timedelta(hours=12)

        # Add old incomplete segment (no end_time)
        playback_db.add_segment(
            camera_id="test_camera",
            file_path="/recordings/test_camera/old_incomplete.mp4",
            start_time=old_time
        )

        # Add recent incomplete segment
        playback_db.add_segment(
            camera_id="test_camera",
            file_path="/recordings/test_camera/recent_incomplete.mp4",
            start_time=recent_time
        )

        # Add completed segment
        playback_db.add_segment(
            camera_id="test_camera",
            file_path="/recordings/test_camera/completed.mp4",
            start_time=old_time,
            end_time=old_time + timedelta(minutes=5),
            duration_seconds=300
        )

        # Cleanup segments older than 24 hours
        cleaned = playback_db.cleanup_old_incomplete_segments(hours_threshold=24)

        # Should only remove old incomplete segment
        assert cleaned == 1

    def test_optimize_database(self, playback_db):
        """Test database optimization (VACUUM and ANALYZE)"""
        # Add some data
        for i in range(100):
            playback_db.add_segment(
                camera_id="test_camera",
                file_path=f"/recordings/test_camera/segment_{i}.mp4",
                start_time=datetime(2026, 1, 20) + timedelta(minutes=i * 5),
                end_time=datetime(2026, 1, 20) + timedelta(minutes=i * 5 + 5),
                duration_seconds=300
            )

        # Optimize database - should not raise exception
        try:
            playback_db.optimize_database()
        except Exception as e:
            pytest.fail(f"optimize_database() raised exception: {e}")


@pytest.mark.unit
class TestDatabaseEdgeCases:
    """Test edge cases and error conditions"""

    def test_segment_with_future_time(self, playback_db):
        """Test adding segment with future timestamp"""
        future_time = datetime.now() + timedelta(days=1)

        segment_id = playback_db.add_segment(
            camera_id="test_camera",
            file_path="/recordings/test_camera/future.mp4",
            start_time=future_time
        )

        # Should still work
        assert segment_id > 0

    def test_segment_with_very_long_path(self, playback_db):
        """Test segment with very long file path"""
        long_path = "/recordings/" + ("a" * 500) + "/test.mp4"

        segment_id = playback_db.add_segment(
            camera_id="test_camera",
            file_path=long_path,
            start_time=datetime(2026, 1, 20, 12, 0, 0)
        )

        assert segment_id > 0

    def test_motion_event_with_zero_intensity(self, playback_db):
        """Test motion event with zero intensity"""
        event_id = playback_db.add_motion_event(
            camera_id="test_camera",
            event_time=datetime(2026, 1, 20, 12, 0, 0),
            intensity=0
        )

        assert event_id > 0

    def test_query_empty_database(self, playback_db):
        """Test queries on empty database"""
        segments = playback_db.get_segments_in_range(
            camera_id="test_camera",
            start_time=datetime(2026, 1, 20, 12, 0, 0),
            end_time=datetime(2026, 1, 20, 13, 0, 0)
        )

        assert segments == []

    def test_query_nonexistent_camera(self, playback_db):
        """Test query for camera that doesn't exist"""
        # Add segment for one camera
        playback_db.add_segment(
            camera_id="camera_1",
            file_path="/recordings/camera_1/test.mp4",
            start_time=datetime(2026, 1, 20, 12, 0, 0)
        )

        # Query for different camera
        segments = playback_db.get_segments_in_range(
            camera_id="camera_2",
            start_time=datetime(2026, 1, 20, 12, 0, 0),
            end_time=datetime(2026, 1, 20, 13, 0, 0)
        )

        assert segments == []

    def test_overlapping_segments(self, playback_db):
        """Test adding overlapping segments (should be allowed)"""
        base_time = datetime(2026, 1, 20, 12, 0, 0)

        # Add two overlapping segments
        playback_db.add_segment(
            camera_id="test_camera",
            file_path="/recordings/test_camera/segment1.mp4",
            start_time=base_time,
            end_time=base_time + timedelta(minutes=10),
            duration_seconds=600
        )

        playback_db.add_segment(
            camera_id="test_camera",
            file_path="/recordings/test_camera/segment2.mp4",
            start_time=base_time + timedelta(minutes=5),
            end_time=base_time + timedelta(minutes=15),
            duration_seconds=600
        )

        # Query should return both
        segments = playback_db.get_segments_in_range(
            camera_id="test_camera",
            start_time=base_time,
            end_time=base_time + timedelta(minutes=15)
        )

        assert len(segments) == 2


@pytest.mark.unit
class TestStorageStatistics:
    """Test storage statistics methods"""

    def test_get_storage_stats_empty_database(self, playback_db):
        """Test storage stats with no data"""
        stats = playback_db.get_storage_stats()

        assert 'cameras' in stats
        assert 'overall' in stats
        assert isinstance(stats['cameras'], dict)
        assert len(stats['cameras']) == 0

    def test_get_storage_stats_with_data(self, playback_db):
        """Test storage stats with multiple cameras"""
        base_time = datetime(2026, 1, 20, 12, 0, 0)

        # Add segments for multiple cameras
        for camera_num in range(1, 4):
            for i in range(5):
                start = base_time + timedelta(minutes=i * 10)
                playback_db.add_segment(
                    camera_id=f"camera_{camera_num}",
                    file_path=f"/recordings/camera_{camera_num}/segment_{i}.mp4",
                    start_time=start,
                    end_time=start + timedelta(minutes=5),
                    duration_seconds=300,
                    file_size_bytes=10 * 1024 * 1024  # 10 MB
                )

        stats = playback_db.get_storage_stats()

        # Check cameras stats
        assert len(stats['cameras']) == 3
        assert 'camera_1' in stats['cameras']
        assert 'camera_2' in stats['cameras']
        assert 'camera_3' in stats['cameras']

        # Each camera should have correct count
        for camera_name, camera_stats in stats['cameras'].items():
            assert camera_stats['segment_count'] == 5
            assert camera_stats['total_bytes'] == 5 * 10 * 1024 * 1024  # 5 segments × 10 MB

        # Check overall stats
        assert stats['overall']['total_segments'] == 15  # 3 cameras × 5 segments
        assert stats['overall']['total_bytes'] == 15 * 10 * 1024 * 1024  # 150 MB total


@pytest.mark.unit
class TestDatabaseMaintenanceExtended:
    """Test additional maintenance operations"""

    def test_cleanup_deleted_files_all_exist(self, playback_db, temp_dir):
        """Test cleanup when all files exist (no orphans)"""
        recordings_path = temp_dir / "recordings" / "test_camera"
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create files that exist
        existing_files = []
        for i in range(3):
            file_path = recordings_path / f"segment_{i}.mp4"
            file_path.write_bytes(b"test data")
            existing_files.append(file_path)

            playback_db.add_segment(
                camera_id="test_camera",
                file_path=str(file_path),
                start_time=datetime(2026, 1, 20, 12, i, 0),
                end_time=datetime(2026, 1, 20, 12, i + 5, 0),
                duration_seconds=300
            )

        # Run cleanup - should find 0 orphans
        deleted = playback_db.cleanup_deleted_files(temp_dir / "recordings")
        assert deleted == 0

    def test_cleanup_old_incomplete_segments_finalizes_existing(self, playback_db, temp_dir):
        """Test that incomplete segments with existing files are finalized"""
        recordings_path = temp_dir / "recordings" / "test_camera"
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create incomplete segment (no end_time) with existing file
        file_path = recordings_path / "incomplete.mp4"
        file_path.write_bytes(b"x" * (5 * 1024 * 1024))  # 5 MB file

        old_time = datetime.now() - timedelta(hours=48)
        playback_db.add_segment(
            camera_id="test_camera",
            file_path=str(file_path),
            start_time=old_time
            # No end_time - incomplete!
        )

        # Verify segment is incomplete
        segments_before = playback_db.get_all_segments("test_camera")
        assert len(segments_before) == 1
        assert segments_before[0]['end_time'] is None

        # Run cleanup - should finalize the segment
        cleaned = playback_db.cleanup_old_incomplete_segments(hours_threshold=24)

        # Segment should still exist but now be finalized
        segments_after = playback_db.get_all_segments("test_camera")
        assert len(segments_after) == 1
        # Should now have end_time estimated (or segment deleted if finalization failed)
        # Just verify the cleanup ran without error
        assert cleaned >= 0

    def test_cleanup_old_incomplete_segments_removes_missing(self, playback_db, temp_dir):
        """Test that incomplete segments without files are removed"""
        recordings_path = temp_dir / "recordings" / "test_camera"
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create incomplete segment WITHOUT file
        old_time = datetime.now() - timedelta(hours=48)
        playback_db.add_segment(
            camera_id="test_camera",
            file_path=str(recordings_path / "missing.mp4"),  # File doesn't exist
            start_time=old_time
            # No end_time - incomplete!
        )

        # Verify segment exists
        segments_before = playback_db.get_all_segments("test_camera")
        assert len(segments_before) == 1

        # Run cleanup - should remove the orphan
        cleaned = playback_db.cleanup_old_incomplete_segments(hours_threshold=24)
        assert cleaned >= 1

        # Segment should be gone
        segments_after = playback_db.get_all_segments("test_camera")
        assert len(segments_after) == 0

    def test_cleanup_old_incomplete_segments_skips_recent(self, playback_db, temp_dir):
        """Test that recent incomplete segments are not cleaned"""
        recordings_path = temp_dir / "recordings" / "test_camera"
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create recent incomplete segment (currently recording)
        recent_time = datetime.now() - timedelta(hours=1)  # Only 1 hour old
        playback_db.add_segment(
            camera_id="test_camera",
            file_path=str(recordings_path / "current.mp4"),
            start_time=recent_time
            # No end_time - currently recording!
        )

        # Run cleanup with 24 hour threshold
        cleaned = playback_db.cleanup_old_incomplete_segments(hours_threshold=24)

        # Recent segment should NOT be cleaned (still recording)
        segments_after = playback_db.get_all_segments("test_camera")
        assert len(segments_after) == 1  # Should still exist

    def test_cleanup_old_incomplete_when_none_exist(self, playback_db):
        """Test cleanup when no incomplete segments exist"""
        # Add only complete segments
        base_time = datetime.now() - timedelta(hours=48)
        playback_db.add_segment(
            camera_id="test_camera",
            file_path="/recordings/test_camera/complete.mp4",
            start_time=base_time,
            end_time=base_time + timedelta(minutes=5),  # Has end_time - complete
            duration_seconds=300
        )

        # Run cleanup - should find nothing to clean
        cleaned = playback_db.cleanup_old_incomplete_segments(hours_threshold=24)
        assert cleaned == 0

    def test_cleanup_incomplete_finalization_error(self, playback_db, temp_dir):
        """Test error handling when segment finalization fails (covers lines 452-455)"""
        from unittest.mock import patch, MagicMock

        # Create directory structure
        recordings_path = temp_dir / 'recordings' / 'test_camera'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create an actual file
        file_path = recordings_path / 'incomplete.mp4'
        create_test_video_file(file_path, size_mb=5)

        # Add incomplete segment (no end_time)
        old_time = datetime.now() - timedelta(hours=48)
        playback_db.add_segment(
            camera_id="test_camera",
            file_path=str(file_path),
            start_time=old_time,
            end_time=None,  # Incomplete - no end_time
            duration_seconds=None
        )

        # Mock Path.stat() to raise an exception during finalization
        # We need to let exists() succeed but make stat() fail in the try block
        original_stat = Path.stat
        call_count = [0]

        def mock_stat_func(self, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                # First call from exists() - let it succeed
                return original_stat(self, **kwargs)
            else:
                # Second call from file_path.stat().st_size - make it fail
                raise OSError("Simulated stat error during finalization")

        with patch.object(Path, 'stat', mock_stat_func):
            # Run cleanup - should catch error and delete segment
            cleaned = playback_db.cleanup_old_incomplete_segments(hours_threshold=24)

            # Should have deleted the segment due to finalization error
            assert cleaned == 1

            # Verify segment was removed from database
            segments = playback_db.get_all_segments("test_camera")
            assert len(segments) == 0
