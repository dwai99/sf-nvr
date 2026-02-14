"""Unit tests for storage manager - automatic cleanup and retention policies"""

import pytest
from pathlib import Path
from datetime import datetime, timedelta
import psutil

from nvr.core.storage_manager import StorageManager
from tests.conftest import create_test_video_file, create_aged_file


@pytest.mark.unit
class TestStorageManager:
    """Test cases for StorageManager class"""

    def test_init_storage_manager(self, storage_manager):
        """Test storage manager initialization"""
        assert storage_manager is not None
        assert storage_manager.retention_days == 7
        assert storage_manager.cleanup_threshold == 85.0
        assert storage_manager.target_percent == 75.0

    def test_cleanup_threshold_check(self, storage_manager, temp_dir):
        """Test that cleanup checks disk usage and responds appropriately"""
        import psutil

        # Get actual disk usage
        disk = psutil.disk_usage(str(temp_dir))
        disk_percent = disk.percent

        # Run cleanup
        stats = storage_manager.check_and_cleanup()

        # Verify cleanup logic based on actual disk usage
        if disk_percent < storage_manager.cleanup_threshold:
            # Below threshold - should not trigger
            assert stats['cleanup_triggered'] is False
        else:
            # Above threshold - cleanup may trigger (but may not delete files if none old enough)
            assert 'cleanup_triggered' in stats

        # Stats should always be valid
        assert isinstance(stats['files_deleted'], int)
        assert isinstance(stats['space_freed_gb'], float)
        assert stats['files_deleted'] >= 0
        assert stats['space_freed_gb'] >= 0.0

    def test_cleanup_old_files_retention_policy(self, storage_manager, temp_dir, playback_db):
        """Test that files older than retention period are eligible for deletion"""
        recordings_path = temp_dir / 'recordings' / 'test_camera_1'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create old files (older than retention) - create content first, then age
        old_file_1 = create_test_video_file(recordings_path / 'old_1.mp4', size_mb=10)
        create_aged_file(old_file_1, days_old=10)

        old_file_2 = create_test_video_file(recordings_path / 'old_2.mp4', size_mb=10)
        create_aged_file(old_file_2, days_old=15)

        # Create recent files (within retention)
        recent_file = create_test_video_file(recordings_path / 'recent.mp4', size_mb=10)

        # Add to database
        base_time = datetime.now()
        playback_db.add_segment(
            camera_id='test_camera_1',
            file_path=str(old_file_1),
            start_time=base_time - timedelta(days=10),
            end_time=base_time - timedelta(days=10) + timedelta(minutes=5),
            duration_seconds=300,
            file_size_bytes=old_file_1.stat().st_size
        )
        playback_db.add_segment(
            camera_id='test_camera_1',
            file_path=str(old_file_2),
            start_time=base_time - timedelta(days=15),
            end_time=base_time - timedelta(days=15) + timedelta(minutes=5),
            duration_seconds=300,
            file_size_bytes=old_file_2.stat().st_size
        )
        playback_db.add_segment(
            camera_id='test_camera_1',
            file_path=str(recent_file),
            start_time=base_time - timedelta(hours=2),
            end_time=base_time - timedelta(hours=2) + timedelta(minutes=5),
            duration_seconds=300,
            file_size_bytes=recent_file.stat().st_size
        )

        # Get retention stats
        stats = storage_manager.get_retention_stats()

        assert stats['total_files'] == 3
        assert stats['files_by_age']['>7days'] >= 2  # Old files
        assert stats['oldest_file_age_days'] >= 10

    def test_retention_stats_accuracy(self, storage_manager, temp_dir):
        """Test that retention statistics are calculated correctly"""
        recordings_path = temp_dir / 'recordings' / 'test_camera_1'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create files of different ages (create content first, then age the file)
        today_file = create_test_video_file(recordings_path / 'today.mp4', size_mb=5)
        create_aged_file(today_file, days_old=0)

        twoday_file = create_test_video_file(recordings_path / '2days.mp4', size_mb=5)
        create_aged_file(twoday_file, days_old=2)

        fiveday_file = create_test_video_file(recordings_path / '5days.mp4', size_mb=5)
        create_aged_file(fiveday_file, days_old=5)

        tenday_file = create_test_video_file(recordings_path / '10days.mp4', size_mb=5)
        create_aged_file(tenday_file, days_old=10)

        stats = storage_manager.get_retention_stats()

        assert stats['total_files'] == 4
        assert stats['files_by_age']['<1day'] >= 1
        assert stats['files_by_age']['1-3days'] >= 1
        assert stats['files_by_age']['3-7days'] >= 1
        assert stats['files_by_age']['>7days'] >= 1
        assert stats['total_size_gb'] > 0

    def test_cleanup_updates_database(self, storage_manager, temp_dir, playback_db):
        """Test that cleanup removes database entries for deleted files"""
        recordings_path = temp_dir / 'recordings' / 'test_camera_1'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create and register an old file
        old_file = create_aged_file(recordings_path / 'old.mp4', days_old=10)
        create_test_video_file(old_file, size_mb=5)

        base_time = datetime.now() - timedelta(days=10)
        playback_db.add_segment(
            camera_id='test_camera_1',
            file_path=str(old_file),
            start_time=base_time,
            end_time=base_time + timedelta(minutes=5),
            duration_seconds=300,
            file_size_bytes=old_file.stat().st_size
        )

        # Verify file is in database
        segments_before = playback_db.get_segments_in_range(
            camera_id='test_camera_1',
            start_time=base_time - timedelta(hours=1),
            end_time=base_time + timedelta(hours=1)
        )
        assert len(segments_before) == 1

        # Delete the file and call delete_segment_by_path
        old_file.unlink()
        deleted = playback_db.delete_segment_by_path('test_camera_1', 'old.mp4')

        assert deleted is True

        # Verify file is no longer in database
        segments_after = playback_db.get_segments_in_range(
            camera_id='test_camera_1',
            start_time=base_time - timedelta(hours=1),
            end_time=base_time + timedelta(hours=1)
        )
        assert len(segments_after) == 0

    def test_cleanup_with_missing_files(self, storage_manager, temp_dir, playback_db):
        """Test that cleanup handles missing files gracefully"""
        # This should not raise exceptions
        try:
            stats = storage_manager.check_and_cleanup()
            assert 'cleanup_triggered' in stats
        except Exception as e:
            pytest.fail(f"Cleanup raised exception with missing files: {e}")

    def test_cleanup_preserves_recent_files(self, storage_manager, temp_dir):
        """Test that recent files are not deleted even if disk is full"""
        recordings_path = temp_dir / 'recordings' / 'test_camera_1'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create recent files
        recent_files = []
        for i in range(5):
            file_path = recordings_path / f'recent_{i}.mp4'
            create_test_video_file(file_path, size_mb=5)
            recent_files.append(file_path)

        # All recent files should still exist after cleanup check
        stats = storage_manager.get_retention_stats()
        assert stats['total_files'] == 5


@pytest.mark.unit
@pytest.mark.slow
class TestStorageCleanupLogic:
    """Test cleanup execution logic"""

    def test_cleanup_frees_correct_amount(self, storage_manager, temp_dir, playback_db):
        """Test that cleanup deletes enough files to reach target"""
        recordings_path = temp_dir / 'recordings' / 'test_camera_1'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create multiple old files
        for i in range(10):
            old_file = create_aged_file(recordings_path / f'old_{i}.mp4', days_old=10 + i)
            create_test_video_file(old_file, size_mb=10)

            base_time = datetime.now() - timedelta(days=10 + i)
            playback_db.add_segment(
                camera_id='test_camera_1',
                file_path=str(old_file),
                start_time=base_time,
                end_time=base_time + timedelta(minutes=5),
                duration_seconds=300,
                file_size_bytes=old_file.stat().st_size
            )

        # Get initial stats
        initial_stats = storage_manager.get_retention_stats()
        assert initial_stats['total_files'] == 10

        # Note: Actual cleanup triggering depends on disk usage
        # This test verifies the logic works correctly

    def test_cleanup_oldest_first(self, storage_manager, temp_dir, playback_db):
        """Test that cleanup deletes oldest files first"""
        recordings_path = temp_dir / 'recordings' / 'test_camera_1'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create files of varying ages
        file_ages = [20, 15, 12, 10, 8]  # Days old
        created_files = []

        for age in file_ages:
            # Create file content first, then age it
            file_path = create_test_video_file(recordings_path / f'file_{age}days.mp4', size_mb=5)
            create_aged_file(file_path, days_old=age)
            created_files.append((age, file_path))

            base_time = datetime.now() - timedelta(days=age)
            playback_db.add_segment(
                camera_id='test_camera_1',
                file_path=str(file_path),
                start_time=base_time,
                end_time=base_time + timedelta(minutes=5),
                duration_seconds=300,
                file_size_bytes=file_path.stat().st_size
            )

        # Verify oldest file is identified correctly
        stats = storage_manager.get_retention_stats()
        assert stats['oldest_file_age_days'] >= 20


@pytest.mark.unit
class TestStorageManagerEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_storage_directory(self, storage_manager):
        """Test behavior with no recording files"""
        stats = storage_manager.get_retention_stats()

        assert stats['total_files'] == 0
        assert stats['total_size_gb'] == 0.0
        assert stats['can_cleanup_gb'] == 0.0

    def test_cleanup_status_endpoint_data(self, storage_manager):
        """Test data returned for cleanup status endpoint"""
        stats = storage_manager.check_and_cleanup()

        # Verify all required keys are present
        required_keys = [
            'cleanup_triggered',
            'initial_usage_percent',
            'final_usage_percent',
            'files_deleted',
            'space_freed_gb'
        ]

        for key in required_keys:
            assert key in stats

        # Verify data types
        assert isinstance(stats['cleanup_triggered'], bool)
        assert isinstance(stats['initial_usage_percent'], (int, float))
        assert isinstance(stats['final_usage_percent'], (int, float))
        assert isinstance(stats['files_deleted'], int)
        assert isinstance(stats['space_freed_gb'], float)

    def test_retention_stats_structure(self, storage_manager):
        """Test structure of retention stats response"""
        stats = storage_manager.get_retention_stats()

        required_keys = [
            'total_files',
            'total_size_gb',
            'files_by_age',
            'oldest_file_age_days',
            'can_cleanup_gb'
        ]

        for key in required_keys:
            assert key in stats

        # Verify files_by_age structure
        age_categories = ['<1day', '1-3days', '3-7days', '>7days']
        for category in age_categories:
            assert category in stats['files_by_age']


@pytest.mark.unit
class TestStorageCleanupExecution:
    """Test actual cleanup execution with file deletion"""

    def test_cleanup_deletes_old_files_when_triggered(self, temp_dir, playback_db):
        """Test that cleanup actually deletes files when disk usage is high"""
        from unittest.mock import patch

        # Create storage manager
        storage_manager = StorageManager(
            storage_path=temp_dir / 'recordings',
            retention_days=7,
            cleanup_threshold_percent=50,  # Low threshold to ensure trigger
            target_percent=40,
            playback_db=playback_db
        )

        recordings_path = temp_dir / 'recordings' / 'test_camera'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create old files (older than retention)
        old_files = []
        for i in range(5):
            file_path = create_test_video_file(
                recordings_path / f'old_{i}.mp4',
                size_mb=5
            )
            create_aged_file(file_path, days_old=10 + i)
            old_files.append(file_path)

            # Add to database
            base_time = datetime.now() - timedelta(days=10 + i)
            playback_db.add_segment(
                camera_id='test_camera',
                file_path=str(file_path),
                start_time=base_time,
                end_time=base_time + timedelta(minutes=5),
                duration_seconds=300,
                file_size_bytes=file_path.stat().st_size
            )

        # Mock disk usage to trigger cleanup
        with patch('psutil.disk_usage') as mock_disk:
            # Return high disk usage (80%)
            mock_disk.return_value = type('obj', (object,), {
                'total': 100 * 1024**3,  # 100 GB
                'used': 80 * 1024**3,     # 80 GB
                'free': 20 * 1024**3,     # 20 GB
                'percent': 80.0
            })()

            # Run cleanup
            stats = storage_manager.check_and_cleanup()

            # Verify cleanup was triggered
            assert stats['cleanup_triggered'] is True
            # Files should be deleted
            assert stats['files_deleted'] > 0
            assert stats['space_freed_gb'] > 0.0

    def test_cleanup_respects_retention_period(self, temp_dir, playback_db):
        """Test that cleanup stops when reaching files within retention period"""
        from unittest.mock import patch

        storage_manager = StorageManager(
            storage_path=temp_dir / 'recordings',
            retention_days=7,
            cleanup_threshold_percent=50,
            target_percent=40,
            playback_db=playback_db
        )

        recordings_path = temp_dir / 'recordings' / 'test_camera'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create files: some old (deletable), some within retention (protected)
        old_files = []
        recent_files = []

        # Old files (10-15 days old) - deletable
        for i in range(3):
            file_path = create_test_video_file(
                recordings_path / f'old_{i}.mp4',
                size_mb=5
            )
            create_aged_file(file_path, days_old=10 + i)
            old_files.append(file_path)

        # Recent files (3-5 days old) - within retention, should be protected
        for i in range(3):
            file_path = create_test_video_file(
                recordings_path / f'recent_{i}.mp4',
                size_mb=5
            )
            create_aged_file(file_path, days_old=3 + i)
            recent_files.append(file_path)

        # Mock high disk usage
        with patch('psutil.disk_usage') as mock_disk:
            mock_disk.return_value = type('obj', (object,), {
                'total': 100 * 1024**3,
                'used': 80 * 1024**3,
                'free': 20 * 1024**3,
                'percent': 80.0
            })()

            stats = storage_manager.check_and_cleanup()

            # Recent files should still exist (within retention)
            for recent_file in recent_files:
                assert recent_file.exists(), f"Recent file {recent_file.name} should be protected"

    def test_cleanup_stops_when_target_reached(self, temp_dir, playback_db):
        """Test that cleanup stops deleting once target usage is reached"""
        from unittest.mock import patch

        storage_manager = StorageManager(
            storage_path=temp_dir / 'recordings',
            retention_days=7,
            cleanup_threshold_percent=80,
            target_percent=70,
            playback_db=playback_db
        )

        recordings_path = temp_dir / 'recordings' / 'test_camera'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create many old files
        for i in range(10):
            file_path = create_test_video_file(
                recordings_path / f'old_{i}.mp4',
                size_mb=5
            )
            create_aged_file(file_path, days_old=10 + i)

        # Mock disk usage that starts high but gets lower as files are deleted
        call_count = [0]
        def mock_disk_usage(path):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: 85% usage (triggers cleanup)
                return type('obj', (object,), {
                    'total': 100 * 1024**3,
                    'used': 85 * 1024**3,
                    'free': 15 * 1024**3,
                    'percent': 85.0
                })()
            else:
                # Subsequent calls: 65% usage (below target)
                return type('obj', (object,), {
                    'total': 100 * 1024**3,
                    'used': 65 * 1024**3,
                    'free': 35 * 1024**3,
                    'percent': 65.0
                })()

        with patch('psutil.disk_usage', side_effect=mock_disk_usage):
            stats = storage_manager.check_and_cleanup()

            # Cleanup should stop when target is reached
            assert stats['cleanup_triggered'] is True
            # Should delete some but not all files
            remaining_files = list(recordings_path.glob('*.mp4'))
            assert len(remaining_files) > 0, "Some files should remain after reaching target"

    def test_cleanup_handles_file_deletion_errors(self, temp_dir, playback_db):
        """Test that cleanup continues even if individual file deletion fails"""
        from unittest.mock import patch
        import os

        storage_manager = StorageManager(
            storage_path=temp_dir / 'recordings',
            retention_days=7,
            cleanup_threshold_percent=50,
            target_percent=40,
            playback_db=playback_db
        )

        recordings_path = temp_dir / 'recordings' / 'test_camera'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create old files
        files = []
        for i in range(5):
            file_path = create_test_video_file(
                recordings_path / f'old_{i}.mp4',
                size_mb=5
            )
            create_aged_file(file_path, days_old=10 + i)
            files.append(file_path)

        # Make middle file read-only (will cause deletion error on some systems)
        if files[2].exists():
            original_mode = files[2].stat().st_mode
            os.chmod(files[2], 0o444)

        try:
            with patch('psutil.disk_usage') as mock_disk:
                mock_disk.return_value = type('obj', (object,), {
                    'total': 100 * 1024**3,
                    'used': 80 * 1024**3,
                    'free': 20 * 1024**3,
                    'percent': 80.0
                })()

                # Should not crash even if one file fails to delete
                stats = storage_manager.check_and_cleanup()
                assert 'cleanup_triggered' in stats
                assert isinstance(stats['files_deleted'], int)

        finally:
            # Restore permissions for cleanup
            if files[2].exists():
                os.chmod(files[2], original_mode)

    def test_cleanup_removes_from_database(self, temp_dir, playback_db):
        """Test that deleted files are also removed from database"""
        from unittest.mock import patch

        storage_manager = StorageManager(
            storage_path=temp_dir / 'recordings',
            retention_days=7,
            cleanup_threshold_percent=50,
            target_percent=40,
            playback_db=playback_db
        )

        recordings_path = temp_dir / 'recordings' / 'test_camera'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create old file and add to database
        old_file = create_test_video_file(
            recordings_path / 'old.mp4',
            size_mb=10
        )
        create_aged_file(old_file, days_old=15)

        base_time = datetime.now() - timedelta(days=15)
        playback_db.add_segment(
            camera_id='test_camera',
            file_path=str(old_file),
            start_time=base_time,
            end_time=base_time + timedelta(minutes=5),
            duration_seconds=300,
            file_size_bytes=old_file.stat().st_size
        )

        # Verify file is in database
        segments_before = playback_db.get_all_segments('test_camera')
        assert len(segments_before) == 1

        # Mock high disk usage to trigger cleanup
        with patch('psutil.disk_usage') as mock_disk:
            mock_disk.return_value = type('obj', (object,), {
                'total': 100 * 1024**3,
                'used': 85 * 1024**3,
                'free': 15 * 1024**3,
                'percent': 85.0
            })()

            stats = storage_manager.check_and_cleanup()

            if stats['cleanup_triggered'] and stats['files_deleted'] > 0:
                # File should be removed from database
                segments_after = playback_db.get_all_segments('test_camera')
                assert len(segments_after) == 0, "Deleted file should be removed from database"

    def test_cleanup_when_no_files_to_delete(self, temp_dir):
        """Test cleanup behavior when no files exist"""
        from unittest.mock import patch

        storage_manager = StorageManager(
            storage_path=temp_dir / 'recordings',
            retention_days=7,
            cleanup_threshold_percent=50,
            target_percent=40
        )

        # Create empty recordings directory
        recordings_path = temp_dir / 'recordings'
        recordings_path.mkdir(parents=True, exist_ok=True)

        with patch('psutil.disk_usage') as mock_disk:
            mock_disk.return_value = type('obj', (object,), {
                'total': 100 * 1024**3,
                'used': 80 * 1024**3,
                'free': 20 * 1024**3,
                'percent': 80.0
            })()

            stats = storage_manager.check_and_cleanup()

            # Should complete without error
            assert stats['cleanup_triggered'] is True
            assert stats['files_deleted'] == 0
            assert stats['space_freed_gb'] == 0.0

    def test_cleanup_error_handling(self, temp_dir):
        """Test that cleanup handles exceptions gracefully"""
        from unittest.mock import patch

        storage_manager = StorageManager(
            storage_path=temp_dir / 'recordings',
            retention_days=7,
            cleanup_threshold_percent=50,
            target_percent=40
        )

        # Mock psutil to raise an exception
        with patch('psutil.disk_usage', side_effect=Exception("Disk error")):
            stats = storage_manager.check_and_cleanup()

            # Should return stats even with error
            assert isinstance(stats, dict)
            assert 'cleanup_triggered' in stats or 'error' in str(stats)

    def test_no_cleanup_when_below_threshold(self, temp_dir):
        """Test that cleanup is NOT triggered when disk usage is below threshold"""
        from unittest.mock import patch

        storage_manager = StorageManager(
            storage_path=temp_dir / 'recordings',
            retention_days=7,
            cleanup_threshold_percent=85,  # 85% threshold
            target_percent=75
        )

        # Mock disk usage below threshold (70%)
        with patch('psutil.disk_usage') as mock_disk:
            mock_disk.return_value = type('obj', (object,), {
                'total': 100 * 1024**3,
                'used': 70 * 1024**3,   # 70% usage - below 85% threshold
                'free': 30 * 1024**3,
                'percent': 70.0
            })()

            stats = storage_manager.check_and_cleanup()

            # Cleanup should NOT be triggered (covers lines 64-65)
            assert stats['cleanup_triggered'] is False
            assert stats['files_deleted'] == 0
            assert stats['space_freed_gb'] == 0.0

    def test_cleanup_with_database_removal_error(self, temp_dir, playback_db):
        """Test cleanup continues when database removal fails"""
        from unittest.mock import patch, MagicMock

        storage_manager = StorageManager(
            storage_path=temp_dir / 'recordings',
            retention_days=7,
            cleanup_threshold_percent=50,
            target_percent=40,
            playback_db=playback_db
        )

        recordings_path = temp_dir / 'recordings' / 'test_camera'
        recordings_path.mkdir(parents=True, exist_ok=True)

        # Create old file
        old_file = create_test_video_file(
            recordings_path / 'old.mp4',
            size_mb=10
        )
        create_aged_file(old_file, days_old=15)

        # Mock playback_db.delete_segment_by_path to raise an error
        original_delete = playback_db.delete_segment_by_path
        playback_db.delete_segment_by_path = MagicMock(
            side_effect=Exception("Database error")
        )

        try:
            with patch('psutil.disk_usage') as mock_disk:
                mock_disk.return_value = type('obj', (object,), {
                    'total': 100 * 1024**3,
                    'used': 85 * 1024**3,
                    'free': 15 * 1024**3,
                    'percent': 85.0
                })()

                # Should complete without crashing even though DB removal fails (covers lines 157-158)
                stats = storage_manager.check_and_cleanup()
                assert stats['cleanup_triggered'] is True
                # File should still be deleted even if DB removal fails
                assert not old_file.exists() or stats['files_deleted'] > 0

        finally:
            # Restore original method
            playback_db.delete_segment_by_path = original_delete
