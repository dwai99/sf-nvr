#!/usr/bin/env python3
"""Manual database maintenance script for NVR"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from nvr.core.playback_db import PlaybackDatabase
from nvr.core.db_maintenance import run_maintenance
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Run database maintenance tasks"""
    db_path = Path("recordings/playback.db")

    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        sys.exit(1)

    logger.info(f"Running maintenance on database: {db_path}")

    # Initialize database
    playback_db = PlaybackDatabase(db_path)

    # Run maintenance
    results = run_maintenance(playback_db)

    # Print summary
    print("\n=== Maintenance Summary ===")
    print(f"Orphaned file entries cleaned: {results['orphaned_files_cleaned']}")
    print(f"Incomplete segments cleaned: {results['incomplete_segments_cleaned']}")
    print(f"Database optimized: {'Yes' if results['database_optimized'] else 'No'}")
    print("\n✅ Database maintenance completed")


if __name__ == "__main__":
    main()
