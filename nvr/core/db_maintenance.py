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
        'segments_repaired': 0,
        'database_optimized': False
    }

    logger.info("Starting database maintenance...")

    # 1. Repair segments with missing end_times (from crashes/restarts)
    try:
        repair_results = playback_db.repair_missing_end_times()
        results['segments_repaired'] = repair_results.get('repaired', 0)
        logger.info(f"Repaired {results['segments_repaired']} segments with missing end_times")
    except Exception as e:
        logger.error(f"Error repairing segment end_times: {e}")

    # 2. Clean up entries for deleted files
    try:
        from nvr.core.config import config
        storage_path = config.storage_path
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


def schedule_maintenance(playback_db, interval_hours: int = 24, run_on_startup: bool = True):
    """
    Schedule periodic database maintenance

    Args:
        playback_db: PlaybackDatabase instance
        interval_hours: How often to run full maintenance (default: 24 hours)
        run_on_startup: Whether to run maintenance immediately on startup
    """
    import threading
    import time

    def maintenance_loop():
        # Run repair immediately on startup (after short delay for system to stabilize)
        if run_on_startup:
            time.sleep(30)  # Wait 30 seconds for system to stabilize
            try:
                logger.info("Running startup segment repair...")
                repair_results = playback_db.repair_missing_end_times()
                logger.info(f"Startup repair: {repair_results.get('repaired', 0)} segments fixed")
            except Exception as e:
                logger.error(f"Error in startup repair: {e}")

        while True:
            try:
                time.sleep(interval_hours * 3600)  # Convert hours to seconds
                run_maintenance(playback_db)
            except Exception as e:
                logger.error(f"Error in maintenance loop: {e}")

    # Start maintenance thread
    thread = threading.Thread(target=maintenance_loop, daemon=True, name="DBMaintenance")
    thread.start()
    logger.info(f"Database maintenance scheduled every {interval_hours} hours (startup repair enabled: {run_on_startup})")
    return thread


def run_segment_repair(playback_db):
    """
    Run just the segment repair task (for manual trigger or more frequent runs).

    Args:
        playback_db: PlaybackDatabase instance

    Returns:
        Dict with repair results
    """
    logger.info("Running segment repair...")
    try:
        results = playback_db.repair_missing_end_times()
        logger.info(f"Segment repair completed: {results}")
        return results
    except Exception as e:
        logger.error(f"Error in segment repair: {e}")
        return {'repaired': 0, 'failed': 0, 'missing': 0, 'error': str(e)}
