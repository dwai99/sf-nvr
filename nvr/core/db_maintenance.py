"""Database maintenance tasks for NVR system"""

import logging

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
        "orphaned_files_cleaned": 0,
        "incomplete_segments_cleaned": 0,
        "segments_repaired": 0,
        "database_optimized": False,
        "orphan_files_found": 0,
        "orphan_files_deleted": 0,
    }

    logger.info("Starting database maintenance...")

    # 1. Repair segments with missing end_times (from crashes/restarts)
    try:
        repair_results = playback_db.repair_missing_end_times()
        results["segments_repaired"] = repair_results.get("repaired", 0)
        logger.info(f"Repaired {results['segments_repaired']} segments with missing end_times")
    except Exception as e:
        logger.error(f"Error repairing segment end_times: {e}")

    # 2. Clean up entries for deleted files — but ONLY if storage is actually
    # writable/mounted. On a transient unmount every file looks "missing", and
    # cleanup_deleted_files would delete every segment row (mass metadata loss)
    # while the recordings are fine and simply offline.
    try:
        from nvr.core.config import config

        if not config.is_storage_writable():
            logger.warning(
                "Storage not writable/mounted - skipping orphaned-entry cleanup "
                "to avoid wiping segment metadata for offline recordings"
            )
        else:
            storage_path = config.storage_path
            deleted = playback_db.cleanup_deleted_files(storage_path)
            results["orphaned_files_cleaned"] = deleted
            logger.info(f"Cleaned up {deleted} orphaned database entries")
    except Exception as e:
        logger.error(f"Error cleaning up orphaned entries: {e}")

    # 2. Handle old incomplete segments (older than 24 hours)
    try:
        cleaned = playback_db.cleanup_old_incomplete_segments(hours_threshold=24)
        results["incomplete_segments_cleaned"] = cleaned
        logger.info(f"Cleaned up {cleaned} old incomplete segments")
    except Exception as e:
        logger.error(f"Error cleaning up incomplete segments: {e}")

    # 2b. Reclaim on-disk recordings that have no DB row (files taking up space
    # that the app never references). Dry-run by default — it just reports the
    # count/size unless storage.orphan_cleanup_enabled is set. Only runs when
    # storage is mounted (an unmount would make every file look orphaned).
    try:
        from nvr.core.config import config

        if config.is_storage_writable():
            enabled = config.get("storage.orphan_cleanup_enabled", False)
            min_age_hours = config.get("storage.orphan_min_age_hours", 1)
            orphan_result = playback_db.cleanup_orphaned_files(
                config.storage_path,
                dry_run=not enabled,
                min_age_seconds=int(min_age_hours * 3600),
            )
            results["orphan_files_found"] = orphan_result["orphan_count"]
            results["orphan_files_deleted"] = orphan_result["deleted_count"]
    except Exception as e:
        logger.error(f"Error scanning for orphaned files: {e}")

    # 3. Optimize database
    try:
        playback_db.optimize_database()
        results["database_optimized"] = True
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
    logger.info(
        f"Database maintenance scheduled every {interval_hours} hours (startup repair enabled: {run_on_startup})"
    )
    return thread
