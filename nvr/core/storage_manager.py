"""Storage management for automatic cleanup of old recordings"""

import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
import psutil

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages storage cleanup and retention policies"""

    def __init__(
        self,
        storage_path: Path,
        playback_db=None,
        retention_days: int = 7,
        cleanup_threshold_percent: float = 85.0,
        target_percent: float = 75.0
    ):
        """
        Initialize storage manager

        Args:
            storage_path: Path to recordings directory
            playback_db: PlaybackDatabase instance
            retention_days: Maximum age of recordings to keep
            cleanup_threshold_percent: Disk usage % that triggers cleanup
            target_percent: Target disk usage % after cleanup
        """
        self.storage_path = Path(storage_path)
        self.playback_db = playback_db
        self.retention_days = retention_days
        self.cleanup_threshold = cleanup_threshold_percent
        self.target_percent = target_percent

    def check_and_cleanup(self) -> Dict[str, Any]:
        """
        Check disk usage and perform cleanup if needed

        Returns:
            Dict with cleanup statistics
        """
        stats = {
            'cleanup_triggered': False,
            'initial_usage_percent': 0,
            'final_usage_percent': 0,
            'files_deleted': 0,
            'space_freed_gb': 0.0
        }

        try:
            # Check current disk usage
            disk = psutil.disk_usage(str(self.storage_path))
            usage_percent = disk.percent
            stats['initial_usage_percent'] = usage_percent

            logger.info(f"Storage usage: {usage_percent:.1f}% ({disk.used / (1024**3):.1f} GB / {disk.total / (1024**3):.1f} GB)")

            # Check if cleanup is needed
            if usage_percent < self.cleanup_threshold:
                logger.info(f"Disk usage ({usage_percent:.1f}%) below threshold ({self.cleanup_threshold}%), no cleanup needed")
                return stats

            stats['cleanup_triggered'] = True
            logger.warning(f"Disk usage ({usage_percent:.1f}%) exceeds threshold ({self.cleanup_threshold}%), starting cleanup")

            # Perform cleanup
            deleted_files, space_freed = self._cleanup_old_files()
            stats['files_deleted'] = deleted_files
            stats['space_freed_gb'] = space_freed / (1024**3)

            # Check final usage
            disk = psutil.disk_usage(str(self.storage_path))
            stats['final_usage_percent'] = disk.percent

            logger.info(f"Cleanup complete: deleted {deleted_files} files, freed {stats['space_freed_gb']:.2f} GB")
            logger.info(f"Final disk usage: {disk.percent:.1f}%")

        except Exception as e:
            logger.error(f"Error during storage cleanup: {e}")

        return stats

    def _cleanup_old_files(self) -> tuple[int, int]:
        """
        Delete old recording files to free up space

        Returns:
            Tuple of (files_deleted, bytes_freed)
        """
        deleted_count = 0
        bytes_freed = 0

        try:
            # Get all recording files with their timestamps
            files = []
            for video_file in self.storage_path.rglob('*.mp4'):
                if video_file.is_file():
                    stat = video_file.stat()
                    files.append({
                        'path': video_file,
                        'size': stat.st_size,
                        'mtime': datetime.fromtimestamp(stat.st_mtime)
                    })

            # Sort by modification time (oldest first)
            files.sort(key=lambda x: x['mtime'])

            logger.info(f"Found {len(files)} recording files for cleanup consideration")

            # Calculate how much space we need to free
            disk = psutil.disk_usage(str(self.storage_path))
            current_used = disk.used
            target_used = disk.total * (self.target_percent / 100)
            space_to_free = current_used - target_used

            if space_to_free <= 0:
                logger.info("Target usage already met, no files to delete")
                return deleted_count, bytes_freed

            logger.info(f"Need to free {space_to_free / (1024**3):.2f} GB to reach {self.target_percent}% usage")

            # Delete files until we reach target usage or run out of old files
            retention_cutoff = datetime.now() - timedelta(days=self.retention_days)

            for file_info in files:
                # Stop if we've freed enough space
                if bytes_freed >= space_to_free:
                    logger.info(f"Target disk usage reached, stopping cleanup")
                    break

                # Check if file is old enough to delete
                if file_info['mtime'] > retention_cutoff:
                    logger.info(f"Reached files newer than {self.retention_days} days, stopping cleanup")
                    break

                try:
                    # Delete the file
                    file_path = file_info['path']
                    file_size = file_info['size']
                    file_path.unlink()
                    deleted_count += 1
                    bytes_freed += file_size

                    logger.debug(f"Deleted {file_path.name} ({file_size / (1024**2):.1f} MB, age: {(datetime.now() - file_info['mtime']).days} days)")

                    # Remove from database if we have access
                    if self.playback_db:
                        try:
                            # Extract camera ID and filename from path
                            camera_id = file_path.parent.name
                            filename = file_path.name
                            self.playback_db.delete_segment_by_path(camera_id, filename)
                        except Exception as db_err:
                            logger.warning(f"Failed to remove {file_path.name} from database: {db_err}")

                except Exception as e:
                    logger.error(f"Failed to delete {file_info['path']}: {e}")

        except Exception as e:
            logger.error(f"Error during file cleanup: {e}")

        return deleted_count, bytes_freed

    def get_retention_stats(self) -> Dict[str, Any]:
        """
        Get statistics about current retention and cleanup potential

        Returns:
            Dict with retention statistics
        """
        stats = {
            'total_files': 0,
            'total_size_gb': 0.0,
            'files_by_age': {
                '<1day': 0,
                '1-3days': 0,
                '3-7days': 0,
                '>7days': 0
            },
            'oldest_file_age_days': 0,
            'can_cleanup_gb': 0.0
        }

        try:
            now = datetime.now()
            retention_cutoff = now - timedelta(days=self.retention_days)
            total_size = 0
            oldest_time = now
            deletable_size = 0

            for video_file in self.storage_path.rglob('*.mp4'):
                if video_file.is_file():
                    stat = video_file.stat()
                    file_time = datetime.fromtimestamp(stat.st_mtime)
                    file_size = stat.st_size
                    age_days = (now - file_time).days

                    stats['total_files'] += 1
                    total_size += file_size

                    # Track oldest file
                    if file_time < oldest_time:
                        oldest_time = file_time

                    # Categorize by age
                    if age_days < 1:
                        stats['files_by_age']['<1day'] += 1
                    elif age_days < 3:
                        stats['files_by_age']['1-3days'] += 1
                    elif age_days <= 7:
                        stats['files_by_age']['3-7days'] += 1
                    else:
                        stats['files_by_age']['>7days'] += 1

                    # Track deletable files (older than retention)
                    if file_time < retention_cutoff:
                        deletable_size += file_size

            stats['total_size_gb'] = total_size / (1024**3)
            stats['can_cleanup_gb'] = deletable_size / (1024**3)
            stats['oldest_file_age_days'] = (now - oldest_time).days

        except Exception as e:
            logger.error(f"Error getting retention stats: {e}")

        return stats
