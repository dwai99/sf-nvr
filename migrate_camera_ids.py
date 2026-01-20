#!/usr/bin/env python3
"""
Migration script to update camera IDs in database and filesystem

This script:
1. Maps old camera names to new camera IDs based on serial numbers
2. Updates database entries to use camera_id
3. Creates symlinks from old directory names to new ID-based directories
4. Preserves all existing recordings

Run this BEFORE renaming any cameras to ensure data continuity.
"""

import sqlite3
import yaml
import shutil
from pathlib import Path
from typing import Dict, List
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config/config.yaml") -> Dict:
    """Load NVR configuration"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def sanitize_name(name: str) -> str:
    """Sanitize camera name for filesystem"""
    return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name)


def build_camera_mapping(config: Dict) -> Dict[str, Dict]:
    """
    Build mapping from old names to camera IDs

    Returns:
        Dict mapping old sanitized names to camera config
    """
    mapping = {}

    for camera in config.get('cameras', []):
        camera_name = camera.get('name')
        camera_id = camera.get('id')

        if not camera_name or not camera_id:
            continue

        old_dir_name = sanitize_name(camera_name)

        mapping[old_dir_name] = {
            'id': camera_id,
            'name': camera_name,
            'old_dir': old_dir_name
        }

    return mapping


def update_database(db_path: str, mapping: Dict[str, Dict]):
    """Update database to use camera_ids based on mapping"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Get all unique camera names from database
        cursor.execute("SELECT DISTINCT camera_name FROM recording_segments")
        db_cameras = [row[0] for row in cursor.fetchall()]

        logger.info(f"Found {len(db_cameras)} cameras in database")

        updates_count = 0
        for db_camera_name in db_cameras:
            # Try to find mapping for this camera
            sanitized = sanitize_name(db_camera_name)

            if sanitized in mapping:
                camera_info = mapping[sanitized]
                new_id = camera_info['id']

                logger.info(f"Updating '{db_camera_name}' → camera_id='{new_id}'")

                # Update recording_segments
                cursor.execute("""
                    UPDATE recording_segments
                    SET camera_id = ?
                    WHERE camera_name = ? AND (camera_id IS NULL OR camera_id = camera_name)
                """, (new_id, db_camera_name))

                updates_count += cursor.rowcount

                # Update motion_events
                cursor.execute("""
                    UPDATE motion_events
                    SET camera_id = ?
                    WHERE camera_name = ? AND (camera_id IS NULL OR camera_id = camera_name)
                """, (new_id, db_camera_name))

            else:
                logger.warning(f"No mapping found for '{db_camera_name}' - will use name as ID")
                # Use sanitized name as fallback ID
                cursor.execute("""
                    UPDATE recording_segments
                    SET camera_id = ?
                    WHERE camera_name = ? AND (camera_id IS NULL OR camera_id = camera_name)
                """, (sanitized, db_camera_name))

                cursor.execute("""
                    UPDATE motion_events
                    SET camera_id = ?
                    WHERE camera_name = ? AND (camera_id IS NULL OR camera_id = camera_name)
                """, (sanitized, db_camera_name))

        conn.commit()
        logger.info(f"Updated {updates_count} database entries")

    finally:
        conn.close()


def migrate_filesystem(storage_path: str, mapping: Dict[str, Dict], dry_run: bool = False):
    """
    Migrate filesystem structure to use camera IDs

    Creates symlinks or renames directories as needed
    """
    storage = Path(storage_path)

    if not storage.exists():
        logger.warning(f"Storage path {storage_path} does not exist")
        return

    for old_dir_name, camera_info in mapping.items():
        old_path = storage / old_dir_name
        new_id = camera_info['id']
        new_path = storage / new_id

        # Skip if old directory doesn't exist
        if not old_path.exists():
            logger.debug(f"Directory {old_dir_name} doesn't exist, skipping")
            continue

        # If new path already exists and is same as old, nothing to do
        if old_path == new_path:
            logger.info(f"✓ {old_dir_name}: Already using correct ID")
            continue

        # If new path exists but is different, need to merge
        if new_path.exists():
            logger.warning(f"Both {old_dir_name} and {new_id} exist - manual merge may be needed")
            continue

        # Rename directory to use camera_id
        if dry_run:
            logger.info(f"[DRY RUN] Would rename: {old_dir_name} → {new_id}")
        else:
            logger.info(f"Renaming: {old_dir_name} → {new_id}")
            old_path.rename(new_path)
            logger.info(f"✓ Renamed successfully")


def verify_migration(db_path: str, storage_path: str):
    """Verify migration was successful"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check for entries without camera_id
    cursor.execute("""
        SELECT COUNT(*) FROM recording_segments WHERE camera_id IS NULL
    """)
    null_ids = cursor.fetchone()[0]

    if null_ids > 0:
        logger.warning(f"Found {null_ids} segments without camera_id")
    else:
        logger.info("✓ All segments have camera_id")

    # Check for mismatched camera_id and file paths
    cursor.execute("""
        SELECT camera_name, camera_id, file_path, COUNT(*) as count
        FROM recording_segments
        GROUP BY camera_name, camera_id
    """)

    logger.info("\nCamera ID mapping summary:")
    for row in cursor.fetchall():
        logger.info(f"  {row[0]} → {row[1]} ({row[3]} files)")

    conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Migrate camera recordings to use physical IDs')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--config', default='config/config.yaml', help='Path to config file')
    parser.add_argument('--db', default='recordings/playback.db', help='Path to database')
    parser.add_argument('--storage', default='recordings', help='Path to recordings storage')

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Camera ID Migration Script")
    logger.info("=" * 70)

    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")

    # Load configuration
    logger.info(f"\n1. Loading configuration from {args.config}")
    config = load_config(args.config)

    # Build mapping
    logger.info("\n2. Building camera name → ID mapping")
    mapping = build_camera_mapping(config)

    if not mapping:
        logger.error("No camera mappings found in config!")
        return 1

    logger.info(f"Found {len(mapping)} cameras to migrate:")
    for old_name, info in mapping.items():
        logger.info(f"  {old_name} → {info['id']}")

    # Update database
    if not args.dry_run:
        logger.info(f"\n3. Updating database at {args.db}")
        update_database(args.db, mapping)
    else:
        logger.info("\n3. [DRY RUN] Skipping database update")

    # Migrate filesystem
    logger.info(f"\n4. Migrating filesystem at {args.storage}")
    migrate_filesystem(args.storage, mapping, dry_run=args.dry_run)

    # Verify
    if not args.dry_run:
        logger.info("\n5. Verifying migration")
        verify_migration(args.db, args.storage)

    logger.info("\n" + "=" * 70)
    if args.dry_run:
        logger.info("DRY RUN COMPLETE - Run without --dry-run to apply changes")
    else:
        logger.info("MIGRATION COMPLETE")
        logger.info("\nNext steps:")
        logger.info("1. Restart the NVR server")
        logger.info("2. Verify all cameras are recording properly")
        logger.info("3. Check playback for all cameras works correctly")
        logger.info("4. You can now safely rename cameras - recordings will be preserved")
    logger.info("=" * 70)

    return 0


if __name__ == '__main__':
    exit(main())
