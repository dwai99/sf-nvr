#!/usr/bin/env python3
"""Fix all camera file paths in database to use camera_id directories"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nvr.core.config import config

def fix_camera_paths():
    """Update all file paths to use camera_id instead of camera_name"""
    db_path = config.storage_path / "playback.db"

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all unique camera mappings
    cursor.execute("""
        SELECT DISTINCT camera_name, camera_id
        FROM recording_segments
        WHERE camera_id IS NOT NULL
    """)

    cameras = cursor.fetchall()

    print(f"Found {len(cameras)} cameras to process\n")

    total_updated = 0

    for camera in cameras:
        camera_name = camera['camera_name']
        camera_id = camera['camera_id']

        # Build old path pattern - handle spaces in camera names
        old_path_pattern = f"recordings/{camera_name}/%"
        new_path_prefix = f"recordings/{camera_id}/"

        # Count how many need updating
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM recording_segments
            WHERE camera_id = ?
            AND file_path LIKE ?
            AND file_path NOT LIKE ?
        """, (camera_id, old_path_pattern, f"{new_path_prefix}%"))

        count = cursor.fetchone()['count']

        if count > 0:
            print(f"Camera: {camera_name}")
            print(f"  ID: {camera_id}")
            print(f"  Files to update: {count}")

            # Update the paths
            cursor.execute("""
                UPDATE recording_segments
                SET file_path = REPLACE(file_path, ?, ?)
                WHERE camera_id = ?
                AND file_path LIKE ?
            """, (f"recordings/{camera_name}/", new_path_prefix, camera_id, old_path_pattern))

            updated = cursor.rowcount
            total_updated += updated
            print(f"  ✓ Updated {updated} file paths\n")
        else:
            print(f"Camera: {camera_name} - Already using correct paths\n")

    conn.commit()
    conn.close()

    print(f"\nTotal file paths updated: {total_updated}")

    if total_updated > 0:
        print("\n✅ Database updated successfully!")
        print("⚠️  Restart the NVR server to pick up changes")
    else:
        print("\n✅ All cameras already using correct paths")

if __name__ == "__main__":
    fix_camera_paths()
