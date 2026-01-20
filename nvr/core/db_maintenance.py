"""Database maintenance tasks for NVR system"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def run_maintenance(playback_db):
    """
    Run all database maintenance tasks

    Args:
        playback_db: PlaybackDatabase instance

    Returns:
        Dict with maintenance results
    """
    results = {
        'orphaned_files_cleaned': 0,
        'incomplete_segments_cleaned': 0,
        'database_optimized': False
    }

    logger.info("Starting database maintenance...")

    # 1. Clean up entries for deleted files
    try:
        storage_path = Path("recordings")
        deleted = playback_db.cleanup_deleted_files(storage_path)
        results['orphaned_files_cleaned'] = deleted
        logger.info(f"Cleaned up {deleted} orphaned database entries")
    except Exception as e:
        logger.error(f"Error cleaning up orphaned entries: {e}")

    # 2. Handle old incomplete segments (older than 24 hours)
    try:
        cleaned = playback_db.cleanup_old_incomplete_segments(hours_threshold=24)
        results['incomplete_segments_cleaned'] = cleaned
        logger.info(f"Cleaned up {cleaned} old incomplete segments")
    except Exception as e:
        logger.error(f"Error cleaning up incomplete segments: {e}")

    # 3. Optimize database
    try:
        playback_db.optimize_database()
        results['database_optimized'] = True
        logger.info("Database optimization completed")
    except Exception as e:
        logger.error(f"Error optimizing database: {e}")

    logger.info(f"Database maintenance completed: {results}")
    return results


def schedule_maintenance(playback_db, interval_hours: int = 24):
    """
    Schedule periodic database maintenance

    Args:
        playback_db: PlaybackDatabase instance
        interval_hours: How often to run maintenance (default: 24 hours)
    """
    import threading
    import time

    def maintenance_loop():
        while True:
            try:
                time.sleep(interval_hours * 3600)  # Convert hours to seconds
                run_maintenance(playback_db)
            except Exception as e:
                logger.error(f"Error in maintenance loop: {e}")

    # Start maintenance thread
    thread = threading.Thread(target=maintenance_loop, daemon=True, name="DBMaintenance")
    thread.start()
    logger.info(f"Database maintenance scheduled every {interval_hours} hours")
    return thread
