"""Background cache cleaner for transcoded video files"""

import threading
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CacheCleaner:
    """Periodically cleans up old cached transcoded files"""

    def __init__(self, cache_dir: str = "recordings/.transcoded", max_age_minutes: int = 60, check_interval_minutes: int = 10):
        """
        Initialize cache cleaner

        Args:
            cache_dir: Directory containing cached files
            max_age_minutes: Delete files older than this many minutes
            check_interval_minutes: How often to check for old files
        """
        self.cache_dir = Path(cache_dir)
        self.max_age_seconds = max_age_minutes * 60
        self.check_interval_seconds = check_interval_minutes * 60
        self.running = False
        self.worker_thread = None

    def start(self):
        """Start the background cache cleaner"""
        if self.running:
            return

        self.running = True
        self.worker_thread = threading.Thread(
            target=self._cleanup_loop,
            name="CacheCleaner",
            daemon=True
        )
        self.worker_thread.start()
        logger.info(f"Cache cleaner started (max age: {self.max_age_seconds // 60} minutes, check interval: {self.check_interval_seconds // 60} minutes)")

    def stop(self):
        """Stop the background cache cleaner"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("Cache cleaner stopped")

    def _cleanup_loop(self):
        """Background loop that periodically cleans old cache files"""
        while self.running:
            try:
                self._cleanup_old_files()
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")

            # Sleep in small increments to allow quick shutdown
            for _ in range(self.check_interval_seconds):
                if not self.running:
                    break
                time.sleep(1)

    def _cleanup_old_files(self):
        """Remove cached files older than max_age"""
        if not self.cache_dir.exists():
            return

        now = time.time()
        deleted_count = 0
        freed_space = 0

        try:
            for file_path in self.cache_dir.glob("*.mp4"):
                try:
                    # Get file age
                    file_age = now - file_path.stat().st_mtime

                    if file_age > self.max_age_seconds:
                        # File is too old, delete it
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        deleted_count += 1
                        freed_space += file_size
                        logger.debug(f"Deleted old cache file: {file_path.name} (age: {file_age // 60:.0f} minutes)")

                except Exception as e:
                    logger.warning(f"Failed to delete cache file {file_path.name}: {e}")

            if deleted_count > 0:
                freed_mb = freed_space / (1024 * 1024)
                logger.info(f"Cache cleanup: Deleted {deleted_count} files, freed {freed_mb:.1f}MB")

        except Exception as e:
            logger.error(f"Error scanning cache directory: {e}")


# Global cache cleaner instance
_cache_cleaner = None


def get_cache_cleaner() -> CacheCleaner:
    """Get or create global cache cleaner instance"""
    global _cache_cleaner
    if _cache_cleaner is None:
        from nvr.core.config import config
        _cache_cleaner = CacheCleaner(
            cache_dir=str(config.storage_path / ".transcoded"),
            max_age_minutes=60,      # Delete files older than 60 minutes
            check_interval_minutes=10  # Check every 10 minutes
        )
        _cache_cleaner.start()
    return _cache_cleaner


def shutdown_cache_cleaner():
    """Shutdown global cache cleaner instance"""
    global _cache_cleaner
    if _cache_cleaner is not None:
        _cache_cleaner.stop()
        _cache_cleaner = None
