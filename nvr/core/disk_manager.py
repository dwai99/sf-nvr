"""
Disk space management to prevent drive from filling up completely
"""
import logging
import os
import shutil
from pathlib import Path
from datetime import datetime
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
                'total_gb': round(usage.total / (1024**3), 2),
                'used_gb': round(usage.used / (1024**3), 2),
                'free_gb': round(usage.free / (1024**3), 2),
                'percent': usage.percent
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
        return usage['percent'] >= self.warning_threshold or usage['free_gb'] < (self.min_free_bytes / (1024**3))
    
    def get_oldest_recordings(self, limit=10):
        """Get oldest recording files sorted by modification time"""
        try:
            files = []
            for root, dirs, filenames in os.walk(self.storage_path):
                for filename in filenames:
                    if filename.endswith('.mp4'):
                        filepath = Path(root) / filename
                        try:
                            mtime = filepath.stat().st_mtime
                            size = filepath.stat().st_size
                            files.append((filepath, mtime, size))
                        except OSError:
                            continue
            
            # Sort by modification time (oldest first)
            files.sort(key=lambda x: x[1])
            return files[:limit]
        except Exception as e:
            logger.error(f"Error getting oldest recordings: {e}")
            return []
    
    def cleanup_old_recordings(self, target_free_gb=None):
        """
        Delete oldest recordings until we have enough free space
        
        Args:
            target_free_gb: Target free space in GB (defaults to min_free_gb + 5)
        
        Returns:
            Number of files deleted and bytes freed
        """
        if target_free_gb is None:
            target_free_gb = (self.min_free_bytes / (1024**3)) + 5  # Add 5GB buffer
        
        target_free_bytes = int(target_free_gb * 1024**3)
        
        usage = self.get_disk_usage()
        if not usage:
            return 0, 0
        
        current_free_bytes = int(usage['free_gb'] * 1024**3)
        
        if current_free_bytes >= target_free_bytes:
            logger.info(f"No cleanup needed. Free space: {usage['free_gb']} GB")
            return 0, 0
        
        bytes_to_free = target_free_bytes - current_free_bytes
        logger.warning(f"Disk cleanup needed! Current free: {usage['free_gb']} GB, Target: {target_free_gb} GB")
        logger.info(f"Need to free {bytes_to_free / (1024**3):.2f} GB")
        
        files_deleted = 0
        bytes_freed = 0
        
        while bytes_freed < bytes_to_free:
            # Get next batch of oldest files
            old_files = self.get_oldest_recordings(limit=50)
            
            if not old_files:
                logger.warning("No more files to delete!")
                break
            
            for filepath, mtime, size in old_files:
                if bytes_freed >= bytes_to_free:
                    break
                
                try:
                    filepath.unlink()
                    files_deleted += 1
                    bytes_freed += size
                    
                    age_days = (datetime.now().timestamp() - mtime) / 86400
                    logger.info(f"Deleted: {filepath.name} (age: {age_days:.1f} days, size: {size/(1024**2):.1f} MB)")
                except OSError as e:
                    logger.error(f"Error deleting {filepath}: {e}")
        
        logger.info(f"Cleanup complete: {files_deleted} files deleted, {bytes_freed/(1024**3):.2f} GB freed")
        
        # Also clean up empty directories
        self._cleanup_empty_dirs()
        
        return files_deleted, bytes_freed
    
    def _cleanup_empty_dirs(self):
        """Remove empty camera directories"""
        try:
            for item in self.storage_path.iterdir():
                if item.is_dir():
                    try:
                        # Try to remove if empty
                        item.rmdir()
                        logger.info(f"Removed empty directory: {item.name}")
                    except OSError:
                        # Directory not empty, that's fine
                        pass
        except Exception as e:
            logger.error(f"Error cleaning empty directories: {e}")
