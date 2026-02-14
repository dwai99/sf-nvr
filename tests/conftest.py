"""Pytest configuration and shared fixtures for SF-NVR tests"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import yaml
import asyncio
from typing import Dict, Any
import sqlite3

# Add project root to Python path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from nvr.core.playback_db import PlaybackDatabase
from nvr.core.storage_manager import StorageManager
from nvr.core.alert_system import AlertSystem
from nvr.core.motion_heatmap import MotionHeatmapManager


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for test files"""
    test_dir = tmp_path / "test_nvr"
    test_dir.mkdir()
    yield test_dir
    # Cleanup
    if test_dir.exists():
        shutil.rmtree(test_dir)


@pytest.fixture
def test_config(temp_dir) -> Dict[str, Any]:
    """Generate test configuration"""
    config_data = {
        'cameras': [
            {
                'id': 'test_camera_1',
                'name': 'Test Camera 1',
                'rtsp_url': 'rtsp://localhost:8554/test1',
                'enabled': True,
                'motion_detection': {
                    'enabled': True,
                    'sensitivity': 25,
                    'min_area': 500
                }
            },
            {
                'id': 'test_camera_2',
                'name': 'Test Camera 2',
                'rtsp_url': 'rtsp://localhost:8554/test2',
                'enabled': True,
                'motion_detection': {
                    'enabled': True,
                    'sensitivity': 30,
                    'min_area': 600
                }
            }
        ],
        'recording': {
            'storage_path': str(temp_dir / 'recordings'),
            'segment_duration': 60,
            'retention_days': 7,
            'cleanup_threshold': 85.0,
            'cleanup_target': 75.0
        },
        'motion': {
            'enabled': True,
            'sensitivity': 25,
            'min_area': 500
        },
        'alerts': {
            'webhook_url': None  # Can be overridden in tests
        },
        'web': {
            'host': '0.0.0.0',
            'port': 8080
        }
    }

    # Create directories
    (temp_dir / 'recordings').mkdir(exist_ok=True)

    # Write config file
    config_path = temp_dir / 'config.yaml'
    with open(config_path, 'w') as f:
        yaml.dump(config_data, f)

    return config_data


@pytest.fixture
def playback_db(temp_dir):
    """Create temporary playback database"""
    db_path = temp_dir / "test_playback.db"
    db = PlaybackDatabase(db_path)  # Pass Path object, not string
    yield db
    # Cleanup - PlaybackDatabase doesn't have close(), just delete the file
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def storage_manager(temp_dir, playback_db):
    """Create storage manager with test configuration"""
    recordings_path = temp_dir / 'recordings'
    recordings_path.mkdir(exist_ok=True)

    manager = StorageManager(
        storage_path=recordings_path,
        playback_db=playback_db,
        retention_days=7,
        cleanup_threshold_percent=85.0,
        target_percent=75.0
    )
    return manager


@pytest.fixture
def alert_system():
    """Create alert system for testing"""
    system = AlertSystem()
    yield system
    # Clear alerts after test
    system.alerts.clear()
    system.alert_cooldowns.clear()
    system.camera_states.clear()


@pytest.fixture
def heatmap_manager(temp_dir, playback_db):
    """Create motion heatmap manager"""
    storage_path = temp_dir / 'recordings'
    storage_path.mkdir(exist_ok=True)

    manager = MotionHeatmapManager(storage_path, playback_db)
    return manager


@pytest.fixture
def sample_recording_segments(temp_dir, playback_db):
    """Create sample recording segments for testing"""
    camera_dir = temp_dir / 'recordings' / 'test_camera_1'
    camera_dir.mkdir(parents=True, exist_ok=True)

    segments = []
    base_time = datetime(2026, 1, 20, 12, 0, 0)

    # Create 10 sample segments
    for i in range(10):
        start_time = base_time + timedelta(minutes=i * 5)
        end_time = start_time + timedelta(minutes=5)

        # Create dummy file
        filename = start_time.strftime("%Y%m%d_%H%M%S.mp4")
        file_path = camera_dir / filename
        file_path.write_bytes(b'dummy video data' * 100)  # ~1.6 KB file

        # Add to database
        playback_db.add_segment(
            camera_id='test_camera_1',
            file_path=str(file_path),
            start_time=start_time,
            end_time=end_time,
            duration_seconds=300,
            file_size_bytes=file_path.stat().st_size
        )

        segments.append({
            'file_path': str(file_path),
            'start_time': start_time,
            'end_time': end_time,
            'filename': filename
        })

    return segments


@pytest.fixture
def sample_motion_events(playback_db):
    """Create sample motion events for testing"""
    camera_id = 'test_camera_1'
    base_time = datetime(2026, 1, 20, 12, 0, 0)

    events = []
    for i in range(20):
        event_time = base_time + timedelta(minutes=i * 3)
        playback_db.add_motion_event(
            camera_id=camera_id,
            event_time=event_time,
            intensity=50 + (i % 50)
        )
        events.append({
            'camera_id': camera_id,
            'event_time': event_time,
            'intensity': 50 + (i % 50)
        })

    return events


@pytest.fixture
def mock_webhook_server():
    """Mock webhook server for alert testing"""
    import responses

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            'http://test.webhook.local/alerts',
            json={'success': True},
            status=200
        )
        yield rsps


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Helper functions for tests

def create_test_video_file(file_path: Path, size_mb: float = 1.0):
    """Create a dummy video file of specified size"""
    size_bytes = int(size_mb * 1024 * 1024)
    file_path.write_bytes(b'\x00' * size_bytes)
    return file_path


def create_aged_file(file_path: Path, days_old: int):
    """Create a file and modify its timestamp to appear older"""
    import os
    import time

    file_path.touch()

    # Calculate timestamp for the past
    old_timestamp = time.time() - (days_old * 24 * 3600)

    # Set access and modification times
    os.utime(file_path, (old_timestamp, old_timestamp))

    return file_path


def populate_database_with_segments(
    playback_db: PlaybackDatabase,
    camera_name: str,
    start_date: datetime,
    num_segments: int,
    segment_duration_minutes: int = 5
) -> list:
    """Populate database with test segments"""
    segments = []

    current_time = start_date
    for i in range(num_segments):
        end_time = current_time + timedelta(minutes=segment_duration_minutes)

        segment_data = {
            'camera_name': camera_name,
            'camera_id': camera_name,
            'file_path': f'/fake/path/{camera_name}/{current_time.strftime("%Y%m%d_%H%M%S")}.mp4',
            'start_time': current_time,
            'end_time': end_time,
            'duration_seconds': segment_duration_minutes * 60,
            'file_size_bytes': 5 * 1024 * 1024  # 5 MB
        }

        playback_db.add_segment(**segment_data)
        segments.append(segment_data)

        current_time = end_time

    return segments
