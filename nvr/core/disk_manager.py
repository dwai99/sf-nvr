"""
Disk space management to prevent drive from filling up completely
"""

import errno
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
import psutil

logger = logging.getLogger(__name__)


class DiskManager:
    """Manages disk space and automatically cleans up old recordings"""

    def __init__(self, storage_path: str, min_free_gb: float = 5.0, warning_threshold_percent: float = 90.0):
        """
        Initialize disk manager

        Args:
            storage_path: Path to recordings directory
            min_free_gb: Minimum free space to maintain (GB)
            warning_threshold_percent: Percentage at which to start warnings
        """
        self.storage_path = Path(storage_path)
        self.min_free_bytes = int(min_free_gb * 1024**3)  # Convert GB to bytes
        self.warning_threshold = warning_threshold_percent

    def get_disk_usage(self):
        """Get current disk usage statistics"""
        try:
            usage = psutil.disk_usage(str(self.storage_path))
            return {
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent": usage.percent,
            }
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return None

    def needs_cleanup(self):
        """Check if cleanup is needed"""
        usage = self.get_disk_usage()
        if not usage:
            return False

        # Need cleanup if:
        # 1. Disk usage is above warning threshold
        # 2. Free space is below minimum
        return usage["percent"] >= self.warning_threshold or usage["free_gb"] < (self.min_free_bytes / (1024**3))

    def get_oldest_recordings(self, limit=None, retention_cutoff=None, protected_paths=None):
        """Get recording files sorted oldest-first.

        Args:
            limit: cap the number returned (None = all candidates)
            retention_cutoff: datetime; files newer than this are excluded (never deleted)
            protected_paths: set of resolved Paths to never return (e.g. active segments)
        """
        protected = protected_paths or set()
        try:
            files = []
            for root, dirs, filenames in os.walk(self.storage_path):
                for filename in filenames:
                    if not filename.endswith(".mp4"):
                        continue
                    filepath = Path(root) / filename
                    try:
                        st = filepath.stat()  # single stat per file
                    except OSError:
                        continue
                    try:
                        resolved = filepath.resolve()
                    except OSError:
                        resolved = filepath
                    if resolved in protected:
                        continue  # actively-writing segment
                    file_time = datetime.fromtimestamp(st.st_mtime)
                    if retention_cutoff is not None and file_time >= retention_cutoff:
                        continue  # within retention window — not a candidate
                    files.append((filepath, st.st_mtime, st.st_size))

            # Sort by modification time (oldest first)
            files.sort(key=lambda x: x[1])
            return files[:limit] if limit else files
        except Exception as e:
            logger.error(f"Error getting oldest recordings: {e}")
            return []

    def cleanup_old_recordings(self, target_free_gb=None, retention_days=None, protected_paths=None):
        """
        Delete oldest recordings until we have enough free space.

        Args:
            target_free_gb: Target free space in GB (defaults to min_free_gb + 5)
            retention_days: If set, never delete recordings newer than this many
                days (prevents emergency cleanup from wiping today's footage).
            protected_paths: Set of resolved Paths to never delete (active segments).

        Returns:
            (files_deleted, bytes_freed)
        """
        if target_free_gb is None:
            target_free_gb = (self.min_free_bytes / (1024**3)) + 5  # Add 5GB buffer

        target_free_bytes = int(target_free_gb * 1024**3)

        usage = self.get_disk_usage()
        if not usage:
            return 0, 0

        current_free_bytes = int(usage["free_gb"] * 1024**3)

        if current_free_bytes >= target_free_bytes:
            logger.info(f"No cleanup needed. Free space: {usage['free_gb']} GB")
            return 0, 0

        bytes_to_free = target_free_bytes - current_free_bytes
        logger.warning(f"Disk cleanup needed! Current free: {usage['free_gb']} GB, Target: {target_free_gb} GB")
        logger.info(f"Need to free {bytes_to_free / (1024**3):.2f} GB")

        retention_cutoff = None
        if retention_days is not None:
            retention_cutoff = datetime.now() - timedelta(days=retention_days)

        # Build the candidate list ONCE (not per-iteration as before, which
        # re-walked the whole volume for every batch), excluding actively-writing
        # segments and anything still within the retention window.
        candidates = self.get_oldest_recordings(
            retention_cutoff=retention_cutoff,
            protected_paths=protected_paths,
        )

        if not candidates:
            logger.warning("No deletable recordings (all within retention or protected)")
            return 0, 0

        files_deleted = 0
        bytes_freed = 0

        for filepath, mtime, size in candidates:
            if bytes_freed >= bytes_to_free:
                break

            try:
                filepath.unlink()
                files_deleted += 1
                bytes_freed += size

                age_days = (datetime.now().timestamp() - mtime) / 86400
                logger.info(f"Deleted: {filepath.name} (age: {age_days:.1f} days, size: {size/(1024**2):.1f} MB)")
            except OSError as e:
                # Read-only / permission-revoked / unmounted volume: abort
                # immediately instead of spinning over thousands of files.
                if e.errno in (errno.EROFS, errno.EACCES, errno.EPERM):
                    logger.error(f"Storage appears unwritable ({e}); aborting cleanup")
                    break
                logger.error(f"Error deleting {filepath}: {e}")

        logger.info(f"Cleanup complete: {files_deleted} files deleted, {bytes_freed/(1024**3):.2f} GB freed")

        # Also clean up empty directories (never active/cache dirs)
        self._cleanup_empty_dirs(protected_paths=protected_paths)

        return files_deleted, bytes_freed

    def _cleanup_empty_dirs(self, protected_paths=None):
        """Remove empty camera directories.

        Skips hidden cache dirs (.transcoded/.speed_cache/.timelapse) and any
        directory currently holding an actively-writing segment — removing the
        latter would break the recorder's next segment open.
        """
        protected_dirs = set()
        for p in protected_paths or set():
            try:
                protected_dirs.add(Path(p).parent.resolve())
            except OSError:
                pass
        try:
            for item in self.storage_path.iterdir():
                if not item.is_dir():
                    continue
                if item.name.startswith("."):
                    continue  # cache dirs
                try:
                    if item.resolve() in protected_dirs:
                        continue
                except OSError:
                    pass
                try:
                    item.rmdir()  # only succeeds if empty
                    logger.info(f"Removed empty directory: {item.name}")
                except OSError:
                    pass  # not empty, that's fine
        except Exception as e:
            logger.error(f"Error cleaning empty directories: {e}")
