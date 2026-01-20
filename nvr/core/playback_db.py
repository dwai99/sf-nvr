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

            # Perform migrations for existing databases
            self._migrate_schema(cursor)

            logger.info(f"Database initialized at {self.db_path}")

    def _migrate_schema(self, cursor):
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

    def add_segment(
        self,
        camera_name: str,
        file_path: str,
        start_time: datetime,
        camera_id: Optional[str] = None,
        end_time: Optional[datetime] = None,
        duration_seconds: Optional[int] = None,
        file_size_bytes: Optional[int] = None,
        fps: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None
    ) -> int:
        """Add a recording segment to the database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO recording_segments
                (camera_name, camera_id, file_path, start_time, end_time, duration_seconds,
                 file_size_bytes, fps, width, height)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                camera_name, camera_id or camera_name, file_path, start_time, end_time,
                duration_seconds, file_size_bytes, fps, width, height
            ))
            return cursor.lastrowid

    def update_segment_end(
        self,
        camera_name: str,
        file_path: str,
        end_time: datetime,
        duration_seconds: int,
        file_size_bytes: int
    ):
        """Update segment end time and metadata after recording completes"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE recording_segments
                SET end_time = ?, duration_seconds = ?, file_size_bytes = ?
                WHERE camera_name = ? AND file_path = ?
            """, (end_time, duration_seconds, file_size_bytes, camera_name, file_path))

    def add_motion_event(
        self,
        camera_name: str,
        event_time: datetime,
        duration_seconds: float = 0.0,
        frame_count: int = 1,
        intensity: float = 0.0,
        event_type: str = 'motion'
    ) -> int:
        """Add a motion/AI detection event"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO motion_events
                (camera_name, event_time, duration_seconds, frame_count, intensity, event_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (camera_name, event_time, duration_seconds, frame_count, intensity, event_type))
            return cursor.lastrowid

    def get_segments_in_range(
        self,
        camera_name: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """Get all recording segments for a camera within a time range"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Find segments that overlap with the requested range:
            # - Segment starts before requested end time
            # - Segment ends after requested start time OR is currently recording (NULL end_time)
            # Support lookup by either camera_name OR camera_id (for compatibility)
            cursor.execute("""
                SELECT * FROM recording_segments
                WHERE (camera_name = ? OR camera_id = ?)
                AND start_time < ?
                AND (end_time > ? OR end_time IS NULL)
                ORDER BY start_time ASC
            """, (camera_name, camera_name, end_time, start_time))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_all_segments(self, camera_name: str) -> List[Dict]:
        """Get all recording segments for a camera, ordered by start time"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Support lookup by either camera_name OR camera_id (for compatibility)
            cursor.execute("""
                SELECT * FROM recording_segments
                WHERE (camera_name = ? OR camera_id = ?)
                ORDER BY start_time ASC
            """, (camera_name, camera_name))

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
                ORDER BY camera_name, start_time ASC
            """, (end_time, start_time))

            rows = cursor.fetchall()

            # Group by camera
            result = {}
            for row in rows:
                camera = row['camera_name']
                if camera not in result:
                    result[camera] = []
                result[camera].append(dict(row))

            return result

    def get_motion_events_in_range(
        self,
        camera_name: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """Get motion events for a camera within a time range"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Support lookup by either camera_name OR camera_id (for compatibility)
            cursor.execute("""
                SELECT * FROM motion_events
                WHERE (camera_name = ? OR camera_id = ?)
                AND event_time BETWEEN ? AND ?
                ORDER BY event_time ASC
            """, (camera_name, camera_name, start_time, end_time))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_all_motion_events_in_range(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, List[Dict]]:
        """Get motion events for all cameras within a time range"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM motion_events
                WHERE event_time BETWEEN ? AND ?
                ORDER BY camera_name, event_time ASC
            """, (start_time, end_time))

            rows = cursor.fetchall()

            # Group by camera
            result = {}
            for row in rows:
                camera = row['camera_name']
                if camera not in result:
                    result[camera] = []
                result[camera].append(dict(row))

            return result

    def get_recording_days(self, camera_name: str) -> List[str]:
        """Get list of dates that have recordings for a camera"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Support lookup by either camera_name OR camera_id (for compatibility)
            cursor.execute("""
                SELECT DISTINCT DATE(start_time) as record_date
                FROM recording_segments
                WHERE (camera_name = ? OR camera_id = ?)
                ORDER BY record_date DESC
            """, (camera_name, camera_name))

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
