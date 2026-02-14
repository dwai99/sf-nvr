"""Database for recording metadata and playback"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class PlaybackDatabase:
    """SQLite database for recording metadata and motion events"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_database(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Recording segments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recording_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    duration_seconds INTEGER,
                    file_size_bytes INTEGER,
                    fps REAL,
                    width INTEGER,
                    height INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(camera_name, file_path)
                )
            """)

            # Index for fast time-range queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_segments_time
                ON recording_segments(camera_name, start_time, end_time)
            """)

            # Index for cross-camera segment queries (no camera filter)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_segments_start_time
                ON recording_segments(start_time)
            """)

            # Motion events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS motion_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_name TEXT NOT NULL,
                    event_time TIMESTAMP NOT NULL,
                    duration_seconds REAL,
                    frame_count INTEGER,
                    intensity REAL,
                    event_type TEXT DEFAULT 'motion',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index for motion event queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_motion_time
                ON motion_events(camera_name, event_time)
            """)

            # Index for cross-camera motion event queries (no camera filter)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_motion_event_time
                ON motion_events(event_time)
            """)

            # Bookmarks table for user-created markers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_name TEXT NOT NULL,
                    camera_id TEXT,
                    timestamp TIMESTAMP NOT NULL,
                    label TEXT,
                    notes TEXT,
                    color TEXT DEFAULT '#ff9500',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index for bookmark queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_bookmarks_time
                ON bookmarks(camera_name, timestamp)
            """)

            # Deletion log table for tracking file cleanup
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS deletion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_name TEXT NOT NULL,
                    camera_id TEXT,
                    file_path TEXT NOT NULL,
                    file_size_bytes INTEGER,
                    recording_start TIMESTAMP,
                    recording_end TIMESTAMP,
                    deletion_reason TEXT,
                    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index for deletion log queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_deletion_time
                ON deletion_log(deleted_at)
            """)

            # Perform migrations for existing databases
            self._migrate_schema(conn, cursor)

            logger.info(f"Database initialized at {self.db_path}")

    def _migrate_schema(self, conn, cursor):
        """Migrate existing database schemas to current version"""
        # Check if event_type column exists in motion_events
        cursor.execute("PRAGMA table_info(motion_events)")
        motion_columns = [row[1] for row in cursor.fetchall()]

        if 'event_type' not in motion_columns:
            logger.info("Migrating motion_events table: adding event_type column")
            cursor.execute("""
                ALTER TABLE motion_events
                ADD COLUMN event_type TEXT DEFAULT 'motion'
            """)
            logger.info("Migration complete: added event_type column")

        # Check if camera_id column exists in recording_segments
        cursor.execute("PRAGMA table_info(recording_segments)")
        segments_columns = [row[1] for row in cursor.fetchall()]

        if 'camera_id' not in segments_columns:
            logger.info("Migrating recording_segments table: adding camera_id column")
            cursor.execute("""
                ALTER TABLE recording_segments
                ADD COLUMN camera_id TEXT
            """)

            # Backfill camera_id with sanitized camera_name for backward compatibility
            cursor.execute("""
                UPDATE recording_segments
                SET camera_id = camera_name
                WHERE camera_id IS NULL
            """)

            # Create index on camera_id
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_segments_camera_id
                ON recording_segments(camera_id, start_time, end_time)
            """)
            logger.info("Migration complete: added camera_id column and index")

        # Check if camera_id column exists in motion_events
        if 'camera_id' not in motion_columns:
            logger.info("Migrating motion_events table: adding camera_id column")
            cursor.execute("""
                ALTER TABLE motion_events
                ADD COLUMN camera_id TEXT
            """)

            # Backfill camera_id with camera_name
            cursor.execute("""
                UPDATE motion_events
                SET camera_id = camera_name
                WHERE camera_id IS NULL
            """)

            # Create index on camera_id
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_motion_camera_id
                ON motion_events(camera_id, event_time)
            """)
            logger.info("Migration complete: added camera_id column to motion_events")

        # Check if camera_id column exists in bookmarks
        cursor.execute("PRAGMA table_info(bookmarks)")
        bookmarks_columns = [row[1] for row in cursor.fetchall()]

        if 'camera_id' not in bookmarks_columns:
            logger.info("Migrating bookmarks table: adding camera_id column")
            cursor.execute("""
                ALTER TABLE bookmarks
                ADD COLUMN camera_id TEXT
            """)
            # Backfill camera_id with camera_name
            cursor.execute("""
                UPDATE bookmarks
                SET camera_id = camera_name
                WHERE camera_id IS NULL
            """)
            logger.info("Migration complete: added camera_id column to bookmarks")

        # Check if camera_id column exists in deletion_log
        cursor.execute("PRAGMA table_info(deletion_log)")
        deletion_columns = [row[1] for row in cursor.fetchall()]

        if 'camera_id' not in deletion_columns:
            logger.info("Migrating deletion_log table: adding camera_id column")
            cursor.execute("""
                ALTER TABLE deletion_log
                ADD COLUMN camera_id TEXT
            """)
            # Backfill camera_id with camera_name
            cursor.execute("""
                UPDATE deletion_log
                SET camera_id = camera_name
                WHERE camera_id IS NULL
            """)
            logger.info("Migration complete: added camera_id column to deletion_log")

        # Check if source column exists in recording_segments (for SD card fallback)
        if 'source' not in segments_columns:
            logger.info("Migrating recording_segments table: adding source column")
            cursor.execute("""
                ALTER TABLE recording_segments
                ADD COLUMN source TEXT DEFAULT 'local'
            """)
            # Backfill existing records as 'local'
            cursor.execute("""
                UPDATE recording_segments
                SET source = 'local'
                WHERE source IS NULL
            """)
            logger.info("Migration complete: added source column for SD card fallback support")

        # Migrate old camera_id values to new format
        self._migrate_camera_ids_to_new_format(conn)

    def _migrate_camera_ids_to_new_format(self, conn):
        """Migrate old camera_id values (names, IP-based) to new unique IDs"""
        try:
            from nvr.core.config import config
            cameras = config.cameras

            if not cameras:
                return

            cursor = conn.cursor()
            total_updated = 0

            for camera in cameras:
                new_id = camera.get('id')
                camera_name = camera.get('name')
                onvif_host = camera.get('onvif_host', '')

                if not new_id or not camera_name:
                    continue

                # Build list of patterns that should map to this camera's new ID
                # Include: exact camera_name match, IP-based patterns, old sanitized names
                old_patterns = [camera_name]

                # Add IP-based patterns if we have the host
                if onvif_host:
                    ip_escaped = onvif_host.replace('.', '_')
                    old_patterns.extend([
                        f"Unknown Camera ({onvif_host})",
                        f"Unknown Camera _{ip_escaped}_",
                        f"cam_{ip_escaped}",
                        onvif_host,
                    ])

                # Update recording_segments - match by camera_name OR old camera_id patterns
                for pattern in old_patterns:
                    # Update where camera_id is old format but camera_name matches current name
                    cursor.execute("""
                        UPDATE recording_segments
                        SET camera_id = ?
                        WHERE camera_id != ? AND (camera_name = ? OR camera_id = ?)
                    """, (new_id, new_id, pattern, pattern))
                    total_updated += cursor.rowcount

                    # Also update motion_events
                    cursor.execute("""
                        UPDATE motion_events
                        SET camera_id = ?
                        WHERE camera_id != ? AND (camera_name = ? OR camera_id = ?)
                    """, (new_id, new_id, pattern, pattern))
                    total_updated += cursor.rowcount

            if total_updated > 0:
                logger.info(f"Migrated {total_updated} records to new camera_id format")

        except Exception as e:
            logger.warning(f"Could not migrate camera IDs (config may not be loaded yet): {e}")

    def migrate_camera_ids(self):
        """Public method to migrate old camera IDs to new format.
        Call this after camera config changes to update historical recordings.
        """
        with self._get_connection() as conn:
            self._migrate_camera_ids_to_new_format(conn)

    def add_segment(
        self,
        camera_id: str,
        file_path: str,
        start_time: datetime,
        camera_name: Optional[str] = None,
        end_time: Optional[datetime] = None,
        duration_seconds: Optional[int] = None,
        file_size_bytes: Optional[int] = None,
        fps: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        source: str = 'local'
    ) -> int:
        """Add a recording segment to the database

        Args:
            camera_id: Unique camera identifier (primary key for lookups)
            file_path: Path to recording file
            start_time: Recording start time
            camera_name: Display name (optional, for backward compatibility)
            source: Recording source - 'local' for NVR storage, 'sd_card' for camera SD card
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO recording_segments
                (camera_id, camera_name, file_path, start_time, end_time, duration_seconds,
                 file_size_bytes, fps, width, height, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                camera_id, camera_name or camera_id, file_path, start_time, end_time,
                duration_seconds, file_size_bytes, fps, width, height, source
            ))
            return cursor.lastrowid

    def update_segment_end(
        self,
        camera_id: str,
        file_path: str,
        end_time: datetime,
        duration_seconds: int,
        file_size_bytes: int
    ):
        """Update segment end time and metadata after recording completes

        Args:
            camera_id: Camera identifier (also matches camera_name for backward compatibility)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Support lookup by camera_id OR camera_name (for backward compatibility)
            cursor.execute("""
                UPDATE recording_segments
                SET end_time = ?, duration_seconds = ?, file_size_bytes = ?
                WHERE (camera_id = ? OR camera_name = ?) AND file_path = ?
            """, (end_time, duration_seconds, file_size_bytes, camera_id, camera_id, file_path))

    def add_motion_event(
        self,
        camera_id: str,
        event_time: datetime,
        duration_seconds: float = 0.0,
        frame_count: int = 1,
        intensity: float = 0.0,
        event_type: str = 'motion',
        camera_name: Optional[str] = None
    ) -> int:
        """Add a motion/AI detection event

        Args:
            camera_id: Unique camera identifier (primary key for lookups)
            camera_name: Display name (optional, for backward compatibility)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO motion_events
                (camera_id, camera_name, event_time, duration_seconds, frame_count, intensity, event_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (camera_id, camera_name or camera_id, event_time, duration_seconds, frame_count, intensity, event_type))
            return cursor.lastrowid

    def get_segments_in_range(
        self,
        camera_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """Get all recording segments for a camera within a time range

        Args:
            camera_id: Camera identifier (also matches camera_name for backward compatibility)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Query by camera_id first (uses index), fallback to camera_name only if needed
            cursor.execute("""
                SELECT * FROM recording_segments
                WHERE camera_id = ?
                AND start_time < ?
                AND (end_time > ? OR end_time IS NULL)
                ORDER BY start_time ASC
            """, (camera_id, end_time, start_time))

            rows = cursor.fetchall()
            if rows:
                return [dict(row) for row in rows]

            # Fallback: try matching by camera_name (backward compatibility)
            cursor.execute("""
                SELECT * FROM recording_segments
                WHERE camera_name = ?
                AND start_time < ?
                AND (end_time > ? OR end_time IS NULL)
                ORDER BY start_time ASC
            """, (camera_id, end_time, start_time))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_all_segments(self, camera_id: str) -> List[Dict]:
        """Get all recording segments for a camera, ordered by start time

        Args:
            camera_id: Camera identifier (also matches camera_name for backward compatibility)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Support lookup by camera_id OR camera_name (for backward compatibility)
            cursor.execute("""
                SELECT * FROM recording_segments
                WHERE (camera_id = ? OR camera_name = ?)
                ORDER BY start_time ASC
            """, (camera_id, camera_id))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_all_segments_in_range(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, List[Dict]]:
        """Get segments for all cameras within a time range"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM recording_segments
                WHERE start_time <= ?
                AND (end_time >= ? OR end_time IS NULL)
                ORDER BY camera_id, start_time ASC
            """, (end_time, start_time))

            rows = cursor.fetchall()

            # Group by camera_id
            result = {}
            for row in rows:
                camera_id = row['camera_id']
                if camera_id not in result:
                    result[camera_id] = []
                result[camera_id].append(dict(row))

            return result

    def get_motion_events_in_range(
        self,
        camera_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """Get motion events for a camera within a time range

        Args:
            camera_id: Camera identifier (also matches camera_name for backward compatibility)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Query by camera_id first (uses index), fallback to camera_name
            cursor.execute("""
                SELECT * FROM motion_events
                WHERE camera_id = ?
                AND event_time BETWEEN ? AND ?
                ORDER BY event_time ASC
            """, (camera_id, start_time, end_time))

            rows = cursor.fetchall()
            if rows:
                return [dict(row) for row in rows]

            # Fallback: try matching by camera_name
            cursor.execute("""
                SELECT * FROM motion_events
                WHERE camera_name = ?
                AND event_time BETWEEN ? AND ?
                ORDER BY event_time ASC
            """, (camera_id, start_time, end_time))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_all_motion_events_in_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 10000
    ) -> Dict[str, List[Dict]]:
        """Get motion events for all cameras within a time range

        Args:
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum events to return (default 10000 for performance)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Select columns needed for timeline visualization including duration
            cursor.execute("""
                SELECT camera_id, event_time, duration_seconds, intensity, event_type
                FROM motion_events
                WHERE event_time BETWEEN ? AND ?
                ORDER BY event_time ASC
                LIMIT ?
            """, (start_time, end_time, limit))

            rows = cursor.fetchall()

            # Group by camera_id
            result = {}
            for row in rows:
                camera_id = row['camera_id']
                if camera_id not in result:
                    result[camera_id] = []
                result[camera_id].append(dict(row))

            return result

    def get_motion_event_counts(
        self,
        start_time: datetime,
        end_time: datetime,
        bucket_minutes: int = 5
    ) -> Dict[str, List[Dict]]:
        """Get aggregated motion event counts per time bucket for all cameras.

        Returns counts per bucket instead of individual events - much faster for timeline overview.
        Keys are camera_id for consistency with other APIs.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # SQLite strftime to bucket events by time interval
            # %s gives Unix timestamp, divide by bucket size to get bucket index
            bucket_seconds = bucket_minutes * 60
            cursor.execute("""
                SELECT
                    camera_id,
                    (CAST(strftime('%s', event_time) AS INTEGER) / ?) * ? AS bucket_start,
                    COUNT(*) as count,
                    AVG(intensity) as avg_intensity
                FROM motion_events
                WHERE event_time BETWEEN ? AND ?
                GROUP BY camera_id, bucket_start
                ORDER BY camera_id, bucket_start
            """, (bucket_seconds, bucket_seconds, start_time, end_time))

            rows = cursor.fetchall()

            # Group by camera, convert bucket_start to ISO timestamp
            # Use utcfromtimestamp because SQLite strftime('%s') treats stored local times as UTC
            result = {}
            for row in rows:
                camera = row['camera_id']
                if camera not in result:
                    result[camera] = []
                result[camera].append({
                    'bucket_time': datetime.utcfromtimestamp(row['bucket_start']).isoformat(),
                    'count': row['count'],
                    'avg_intensity': row['avg_intensity']
                })

            return result

    def get_recording_days(self, camera_id: str) -> List[str]:
        """Get list of dates that have recordings for a camera

        Args:
            camera_id: Camera identifier (also matches camera_name for backward compatibility)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Support lookup by camera_id OR camera_name (for backward compatibility)
            cursor.execute("""
                SELECT DISTINCT DATE(start_time) as record_date
                FROM recording_segments
                WHERE (camera_id = ? OR camera_name = ?)
                ORDER BY record_date DESC
            """, (camera_id, camera_id))

            rows = cursor.fetchall()
            return [row['record_date'] for row in rows]

    def get_storage_stats(self) -> Dict:
        """Get storage statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total size by camera
            cursor.execute("""
                SELECT camera_name,
                       COUNT(*) as segment_count,
                       SUM(file_size_bytes) as total_bytes,
                       MIN(start_time) as oldest_recording,
                       MAX(end_time) as newest_recording
                FROM recording_segments
                GROUP BY camera_name
            """)

            cameras = {}
            for row in cursor.fetchall():
                cameras[row['camera_name']] = dict(row)

            # Overall stats
            cursor.execute("""
                SELECT COUNT(*) as total_segments,
                       SUM(file_size_bytes) as total_bytes,
                       MIN(start_time) as oldest_recording,
                       MAX(end_time) as newest_recording
                FROM recording_segments
            """)

            overall = dict(cursor.fetchone())

            return {
                'cameras': cameras,
                'overall': overall
            }

    def cleanup_deleted_files(self, storage_path: Path) -> int:
        """Remove database entries for files that no longer exist"""
        deleted_count = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, file_path FROM recording_segments")

            for row in cursor.fetchall():
                file_path = Path(row['file_path'])
                if not file_path.exists():
                    conn.execute(
                        "DELETE FROM recording_segments WHERE id = ?",
                        (row['id'],)
                    )
                    deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Removed {deleted_count} orphaned database entries")

        return deleted_count

    def cleanup_old_incomplete_segments(self, hours_threshold: int = 24) -> int:
        """
        Clean up incomplete segments (NULL end_time) that are older than threshold

        These are likely from crashed recordings or server restarts. Only clean up
        segments older than the threshold to avoid removing currently recording segments.

        Args:
            hours_threshold: Age in hours before an incomplete segment is considered orphaned

        Returns:
            Number of segments cleaned up
        """
        from datetime import datetime, timedelta

        threshold_time = datetime.now() - timedelta(hours=hours_threshold)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Find old incomplete segments
            cursor.execute("""
                SELECT id, camera_name, file_path, start_time
                FROM recording_segments
                WHERE end_time IS NULL
                AND start_time < ?
            """, (threshold_time,))

            old_incomplete = cursor.fetchall()

            if not old_incomplete:
                return 0

            deleted_count = 0
            for row in old_incomplete:
                file_path = Path(row['file_path'])

                # If file exists, try to finalize it with actual file info
                if file_path.exists():
                    try:
                        file_size = file_path.stat().st_size
                        # Estimate duration based on file size (rough estimate: ~2MB per minute for 1080p)
                        estimated_duration = max(60, int(file_size / (2 * 1024 * 1024) * 60))
                        estimated_end_time = datetime.fromisoformat(row['start_time']) + timedelta(seconds=estimated_duration)

                        # Update with estimates
                        conn.execute("""
                            UPDATE recording_segments
                            SET end_time = ?,
                                duration_seconds = ?,
                                file_size_bytes = ?
                            WHERE id = ?
                        """, (estimated_end_time, estimated_duration, file_size, row['id']))

                        logger.info(f"Finalized orphaned segment: {file_path.name} (estimated duration: {estimated_duration}s)")
                    except Exception as e:
                        logger.warning(f"Failed to finalize {file_path.name}: {e}")
                        conn.execute("DELETE FROM recording_segments WHERE id = ?", (row['id'],))
                        deleted_count += 1
                else:
                    # File doesn't exist, delete the database entry
                    conn.execute("DELETE FROM recording_segments WHERE id = ?", (row['id'],))
                    deleted_count += 1

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old incomplete segments")

            return deleted_count

    def optimize_database(self):
        """Run database optimization (VACUUM and ANALYZE) for better performance"""
        with self._get_connection() as conn:
            # VACUUM reclaims space and defragments the database
            conn.execute("VACUUM")
            logger.info("Database VACUUM completed")

            # ANALYZE updates statistics for query optimization
            conn.execute("ANALYZE")
            logger.info("Database ANALYZE completed")

    def delete_segment_by_path(self, camera_id: str, filename: str) -> bool:
        """
        Delete a segment from the database by camera_id and filename

        Args:
            camera_id: Camera identifier
            filename: Recording filename (e.g., "20260119_200022.mp4")

        Returns:
            True if segment was deleted, False otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Delete by file_path pattern
            file_path_pattern = f"%/{camera_id}/{filename}"

            cursor.execute("""
                DELETE FROM recording_segments
                WHERE file_path LIKE ?
            """, (file_path_pattern,))

            deleted = cursor.rowcount > 0

            if deleted:
                logger.info(f"Deleted segment from database: {camera_id}/{filename}")

            return deleted

    def log_deletion(
        self,
        camera_id: str,
        file_path: str,
        file_size_bytes: int,
        recording_start: Optional[datetime],
        recording_end: Optional[datetime],
        deletion_reason: str,
        camera_name: Optional[str] = None
    ) -> int:
        """Log a file deletion for audit trail

        Args:
            camera_id: Unique camera identifier (primary key for lookups)
            camera_name: Display name (optional, for backward compatibility)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO deletion_log
                (camera_id, camera_name, file_path, file_size_bytes, recording_start, recording_end, deletion_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (camera_id, camera_name or camera_id, file_path, file_size_bytes, recording_start, recording_end, deletion_reason))
            return cursor.lastrowid

    def delete_motion_events_in_range(
        self,
        camera_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> int:
        """Delete motion events within a time range (when recording is deleted)

        Args:
            camera_id: Camera identifier (also matches camera_name for backward compatibility)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM motion_events
                WHERE (camera_id = ? OR camera_name = ?)
                AND event_time BETWEEN ? AND ?
            """, (camera_id, camera_id, start_time, end_time))
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Deleted {deleted} motion events for {camera_id} from {start_time} to {end_time}")
            return deleted

    def get_deletion_history(
        self,
        limit: int = 100,
        camera_id: Optional[str] = None
    ) -> List[Dict]:
        """Get recent deletion history

        Args:
            limit: Maximum number of records to return
            camera_id: Filter by camera (also matches camera_name for backward compatibility)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if camera_id:
                # Support lookup by camera_id OR camera_name (for backward compatibility)
                cursor.execute("""
                    SELECT * FROM deletion_log
                    WHERE (camera_id = ? OR camera_name = ?)
                    ORDER BY deleted_at DESC
                    LIMIT ?
                """, (camera_id, camera_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM deletion_log
                    ORDER BY deleted_at DESC
                    LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_deletion_stats(self) -> Dict:
        """Get deletion statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total deletions
            cursor.execute("SELECT COUNT(*) as count, SUM(file_size_bytes) as bytes FROM deletion_log")
            total = cursor.fetchone()

            # Deletions in last 24 hours
            cursor.execute("""
                SELECT COUNT(*) as count, SUM(file_size_bytes) as bytes
                FROM deletion_log
                WHERE deleted_at >= datetime('now', '-1 day')
            """)
            last_24h = cursor.fetchone()

            # Deletions in last 7 days
            cursor.execute("""
                SELECT COUNT(*) as count, SUM(file_size_bytes) as bytes
                FROM deletion_log
                WHERE deleted_at >= datetime('now', '-7 days')
            """)
            last_7d = cursor.fetchone()

            return {
                'total_files': total['count'] or 0,
                'total_bytes': total['bytes'] or 0,
                'last_24h_files': last_24h['count'] or 0,
                'last_24h_bytes': last_24h['bytes'] or 0,
                'last_7d_files': last_7d['count'] or 0,
                'last_7d_bytes': last_7d['bytes'] or 0
            }

    def add_bookmark(
        self,
        camera_id: str,
        timestamp: datetime,
        label: Optional[str] = None,
        notes: Optional[str] = None,
        color: str = '#ff9500',
        camera_name: Optional[str] = None
    ) -> int:
        """
        Add a bookmark at a specific timestamp

        Args:
            camera_id: Unique camera identifier (primary key for lookups)
            timestamp: Timestamp for the bookmark
            label: Short label for the bookmark
            notes: Detailed notes/annotation
            color: Hex color code for the marker
            camera_name: Display name (optional, for backward compatibility)

        Returns:
            Bookmark ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO bookmarks (camera_id, camera_name, timestamp, label, notes, color)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (camera_id, camera_name or camera_id, timestamp, label, notes, color))

            bookmark_id = cursor.lastrowid
            logger.info(f"Added bookmark for {camera_id} at {timestamp}")

            return bookmark_id

    def update_bookmark(
        self,
        bookmark_id: int,
        label: Optional[str] = None,
        notes: Optional[str] = None,
        color: Optional[str] = None
    ) -> bool:
        """Update an existing bookmark"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            updates = []
            params = []

            if label is not None:
                updates.append("label = ?")
                params.append(label)

            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)

            if color is not None:
                updates.append("color = ?")
                params.append(color)

            if not updates:
                return False

            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(bookmark_id)

            cursor.execute(f"""
                UPDATE bookmarks
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)

            return cursor.rowcount > 0

    def delete_bookmark(self, bookmark_id: int) -> bool:
        """Delete a bookmark by ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))

            return cursor.rowcount > 0

    def get_bookmarks_in_range(
        self,
        camera_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """Get all bookmarks in a time range for a camera

        Args:
            camera_id: Camera identifier (also matches camera_name for backward compatibility)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Support lookup by camera_id OR camera_name (for backward compatibility)
            cursor.execute("""
                SELECT id, camera_name, camera_id, timestamp, label, notes, color, created_at, updated_at
                FROM bookmarks
                WHERE (camera_id = ? OR camera_name = ?)
                AND timestamp >= ?
                AND timestamp <= ?
                ORDER BY timestamp ASC
            """, (camera_id, camera_id, start_time, end_time))

            bookmarks = []
            for row in cursor.fetchall():
                bookmarks.append({
                    'id': row[0],
                    'camera_name': row[1],
                    'camera_id': row[2],
                    'timestamp': row[3],
                    'label': row[4],
                    'notes': row[5],
                    'color': row[6],
                    'created_at': row[7],
                    'updated_at': row[8]
                })

            return bookmarks

    def get_all_bookmarks_in_range(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """Get all bookmarks across all cameras in a time range"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, camera_name, camera_id, timestamp, label, notes, color, created_at, updated_at
                FROM bookmarks
                WHERE timestamp >= ?
                AND timestamp <= ?
                ORDER BY timestamp ASC
            """, (start_time, end_time))

            bookmarks = []
            for row in cursor.fetchall():
                bookmarks.append({
                    'id': row[0],
                    'camera_name': row[1],
                    'camera_id': row[2],
                    'timestamp': row[3],
                    'label': row[4],
                    'notes': row[5],
                    'color': row[6],
                    'created_at': row[7],
                    'updated_at': row[8]
                })

            return bookmarks

    def repair_missing_end_times(self) -> Dict[str, int]:
        """Repair segments with missing end_times by reading actual video file durations.

        Returns:
            Dict with 'repaired', 'failed', and 'missing' counts
        """
        import subprocess

        results = {'repaired': 0, 'failed': 0, 'missing': 0}

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Find all segments with NULL end_time
            cursor.execute("""
                SELECT id, camera_id, file_path, start_time
                FROM recording_segments
                WHERE end_time IS NULL
            """)

            segments_to_repair = cursor.fetchall()
            logger.info(f"Found {len(segments_to_repair)} segments with missing end_times")

            for row in segments_to_repair:
                segment_id, camera_id, file_path, start_time_str = row
                file_path_obj = Path(file_path)

                if not file_path_obj.exists():
                    logger.warning(f"File not found: {file_path}")
                    results['missing'] += 1
                    continue

                try:
                    # Use ffprobe to get actual video duration
                    result = subprocess.run(
                        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                         '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path_obj)],
                        capture_output=True, text=True, timeout=10
                    )

                    if result.returncode != 0:
                        logger.warning(f"ffprobe failed for {file_path}: {result.stderr}")
                        results['failed'] += 1
                        continue

                    duration_seconds = float(result.stdout.strip())
                    file_size = file_path_obj.stat().st_size

                    # Parse start_time and calculate end_time
                    start_time = datetime.fromisoformat(start_time_str)
                    end_time = start_time + timedelta(seconds=duration_seconds)

                    # Update the database
                    cursor.execute("""
                        UPDATE recording_segments
                        SET end_time = ?, duration_seconds = ?, file_size_bytes = ?
                        WHERE id = ?
                    """, (end_time, int(duration_seconds), file_size, segment_id))

                    logger.info(f"Repaired segment {segment_id}: {file_path} (duration: {duration_seconds:.1f}s)")
                    results['repaired'] += 1

                except subprocess.TimeoutExpired:
                    logger.warning(f"ffprobe timeout for {file_path}")
                    results['failed'] += 1
                except Exception as e:
                    logger.warning(f"Error repairing segment {segment_id}: {e}")
                    results['failed'] += 1

        logger.info(f"Repair complete: {results['repaired']} repaired, {results['failed']} failed, {results['missing']} missing files")
        return results
