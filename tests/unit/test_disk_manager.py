"""Unit tests for DiskManager - cleanup safety (2026-06-02 fixes).

Covers:
- retention_days is honored (emergency cleanup must not delete recent footage)
- actively-writing segments are never deleted (protected_paths)
- a read-only / permission-revoked volume aborts cleanup instead of spinning
- empty-dir cleanup never removes hidden cache dirs or active camera dirs
"""

import errno
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

from nvr.core.disk_manager import DiskManager
from tests.conftest import create_test_video_file, create_aged_file


def _mock_usage(percent, free_gb, total_gb=100):
    return type('obj', (object,), {
        'total': total_gb * 1024**3,
        'used': int(total_gb * percent / 100) * 1024**3,
        'free': int(free_gb) * 1024**3,
        'percent': percent,
    })()


@pytest.mark.unit
class TestDiskManagerRetention:
    """retention_days must protect recent footage from emergency cleanup."""

    def test_cleanup_skips_files_within_retention(self, temp_dir):
        storage = temp_dir / "recordings" / "cam1"
        storage.mkdir(parents=True)

        # A recent file (1 day old) and an old file (10 days old)
        recent = create_test_video_file(storage / "recent.mp4", size_mb=5)
        create_aged_file(recent, days_old=1)
        old = create_test_video_file(storage / "old.mp4", size_mb=5)
        create_aged_file(old, days_old=10)

        dm = DiskManager(str(temp_dir / "recordings"), min_free_gb=5)

        # Disk almost full so cleanup wants to free a lot
        with patch('psutil.disk_usage', return_value=_mock_usage(99, 1)):
            dm.cleanup_old_recordings(target_free_gb=50, retention_days=7)

        assert old.exists() is False, "old file should be deleted"
        assert recent.exists() is True, "file within retention must be kept"

    def test_no_retention_arg_allows_deleting_recent(self, temp_dir):
        """Without retention_days the old behavior (age-agnostic) still works."""
        storage = temp_dir / "recordings" / "cam1"
        storage.mkdir(parents=True)
        recent = create_test_video_file(storage / "recent.mp4", size_mb=5)
        create_aged_file(recent, days_old=1)

        dm = DiskManager(str(temp_dir / "recordings"), min_free_gb=5)
        with patch('psutil.disk_usage', return_value=_mock_usage(99, 1)):
            dm.cleanup_old_recordings(target_free_gb=50)  # no retention_days

        assert recent.exists() is False


@pytest.mark.unit
class TestDiskManagerProtectedPaths:
    """Actively-writing segments must never be deleted."""

    def test_active_segment_not_deleted(self, temp_dir):
        storage = temp_dir / "recordings" / "cam1"
        storage.mkdir(parents=True)
        active = create_test_video_file(storage / "active.mp4", size_mb=5)
        create_aged_file(active, days_old=20)  # old enough to be a candidate
        other = create_test_video_file(storage / "other.mp4", size_mb=5)
        create_aged_file(other, days_old=20)

        dm = DiskManager(str(temp_dir / "recordings"), min_free_gb=5)
        protected = {active.resolve()}

        with patch('psutil.disk_usage', return_value=_mock_usage(99, 1)):
            dm.cleanup_old_recordings(target_free_gb=50, protected_paths=protected)

        assert active.exists() is True, "active segment must be protected"
        assert other.exists() is False


@pytest.mark.unit
class TestDiskManagerUnwritableVolume:
    """A read-only volume must abort cleanup, not spin forever."""

    def test_eperm_aborts_without_infinite_loop(self, temp_dir):
        storage = temp_dir / "recordings" / "cam1"
        storage.mkdir(parents=True)
        for i in range(5):
            f = create_test_video_file(storage / f"old_{i}.mp4", size_mb=5)
            create_aged_file(f, days_old=20)

        dm = DiskManager(str(temp_dir / "recordings"), min_free_gb=5)

        def raise_eperm(self):
            raise PermissionError(errno.EPERM, "Operation not permitted")

        # unlink always fails (read-only volume). Old code would loop forever
        # re-walking; new code aborts after the first EPERM.
        with patch('psutil.disk_usage', return_value=_mock_usage(99, 1)), \
             patch.object(Path, 'unlink', raise_eperm):
            deleted, freed = dm.cleanup_old_recordings(target_free_gb=50, retention_days=7)

        assert deleted == 0
        assert freed == 0


@pytest.mark.unit
class TestDiskManagerEmptyDirs:
    """Empty-dir cleanup must skip cache dirs and active camera dirs."""

    def test_skips_hidden_and_protected_dirs(self, temp_dir):
        root = temp_dir / "recordings"
        root.mkdir(parents=True)
        cache = root / ".transcoded"      # hidden cache dir, empty
        cache.mkdir()
        active_cam = root / "cam_active"   # holds an active segment
        active_cam.mkdir()
        active_seg = active_cam / "live.mp4"
        active_seg.write_bytes(b"")
        empty_cam = root / "cam_empty"     # retired, empty -> ok to remove
        empty_cam.mkdir()

        dm = DiskManager(str(root))
        dm._cleanup_empty_dirs(protected_paths={active_seg.resolve()})

        assert cache.exists() is True, "hidden cache dir must be preserved"
        assert active_cam.exists() is True, "active camera dir must be preserved"
        assert empty_cam.exists() is False, "empty retired dir may be removed"
