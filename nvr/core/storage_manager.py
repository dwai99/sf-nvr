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
        target_percent: float = 75.0,
        reserved_space_gb: float = 0.0
    ):
        """
        Initialize storage manager

        Args:
            storage_path: Path to recordings directory
            playback_db: PlaybackDatabase instance
            retention_days: Maximum age of recordings to keep
            cleanup_threshold_percent: Disk usage % that triggers cleanup
            target_percent: Target disk usage % after cleanup
            reserved_space_gb: Minimum free space in GB to maintain on disk
        """
        self.storage_path = Path(storage_path)
        self.playback_db = playback_db
        self.retention_days = retention_days
        self.cleanup_threshold = cleanup_threshold_percent
        self.target_percent = target_percent
        self.reserved_space_gb = reserved_space_gb

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

            # Check if reserved space is violated
            free_gb = disk.free / (1024**3)
            reserved_violated = self.reserved_space_gb > 0 and free_gb < self.reserved_space_gb

            # Check if cleanup is needed
            if usage_percent < self.cleanup_threshold and not reserved_violated:
                logger.info(f"Disk usage ({usage_percent:.1f}%) below threshold ({self.cleanup_threshold}%), free space {free_gb:.1f} GB, no cleanup needed")
                return stats

            if reserved_violated:
                logger.warning(f"Free space ({free_gb:.1f} GB) below reserved minimum ({self.reserved_space_gb} GB), starting cleanup")

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
            current_usage = disk.percent  # For deletion reason logging
            target_used = disk.total * (self.target_percent / 100)
            space_to_free = current_used - target_used

            # Also ensure reserved space is met
            if self.reserved_space_gb > 0:
                reserved_bytes = self.reserved_space_gb * (1024**3)
                space_needed_for_reserve = reserved_bytes - disk.free
                if space_needed_for_reserve > space_to_free:
                    space_to_free = space_needed_for_reserve

            if space_to_free <= 0:
                logger.info("Target usage already met, no files to delete")
                return deleted_count, bytes_freed

            logger.info(f"Need to free {space_to_free / (1024**3):.2f} GB to reach {self.target_percent}% usage (reserved: {self.reserved_space_gb} GB)")

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
                    camera_id = file_path.parent.name
                    filename = file_path.name

                    # Get segment info before deletion for logging and motion cleanup
                    segment_start = None
                    segment_end = None
                    camera_name = camera_id  # Default to folder name

                    if self.playback_db:
                        try:
                            # Try to get segment details from database
                            segments = self.playback_db.get_all_segments(camera_id)
                            for seg in segments:
                                if filename in seg.get('file_path', ''):
                                    segment_start = datetime.fromisoformat(seg['start_time']) if seg.get('start_time') else None
                                    segment_end = datetime.fromisoformat(seg['end_time']) if seg.get('end_time') else None
                                    camera_name = seg.get('camera_name', camera_id)
                                    break
                        except Exception as e:
                            logger.debug(f"Could not get segment info: {e}")

                    # Delete the file
                    file_path.unlink()
                    deleted_count += 1
                    bytes_freed += file_size

                    age_days = (datetime.now() - file_info['mtime']).days
                    logger.info(f"Deleted {file_path.name} ({file_size / (1024**2):.1f} MB, age: {age_days} days)")

                    # Remove from database and log deletion
                    if self.playback_db:
                        try:
                            # Log the deletion
                            self.playback_db.log_deletion(
                                camera_id=camera_id,
                                file_path=str(file_path),
                                file_size_bytes=file_size,
                                recording_start=segment_start,
                                recording_end=segment_end,
                                deletion_reason=f"Storage cleanup (disk at {current_usage:.1f}%)",
                                camera_name=camera_name
                            )

                            # Delete segment from database
                            self.playback_db.delete_segment_by_path(camera_id, filename)

                            # Delete associated motion events
                            if segment_start and segment_end:
                                self.playback_db.delete_motion_events_in_range(
                                    camera_id, segment_start, segment_end
                                )
                        except Exception as db_err:
                            logger.warning(f"Failed to update database for {file_path.name}: {db_err}")

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
