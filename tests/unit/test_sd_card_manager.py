"""Unit tests for SD Card fallback recording functionality"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path


class TestSDCardRecordingsManager:
    """Tests for SDCardRecordingsManager class"""

    @pytest.fixture
    def mock_playback_db(self):
        """Create mock playback database"""
        db = Mock()
        db.get_segments_in_range = Mock(return_value=[])
        return db

    @pytest.fixture
    def sd_card_manager(self, mock_playback_db):
        """Create SDCardRecordingsManager instance"""
        from nvr.core.sd_card_manager import SDCardRecordingsManager
        return SDCardRecordingsManager(
            playback_db=mock_playback_db,
            cache_duration=300,
            query_timeout=30.0
        )

    def test_sd_card_manager_init(self, mock_playback_db):
        """Test SDCardRecordingsManager initialization"""
        from nvr.core.sd_card_manager import SDCardRecordingsManager

        manager = SDCardRecordingsManager(
            playback_db=mock_playback_db,
            cache_duration=600,
            query_timeout=45.0
        )

        assert manager.playback_db == mock_playback_db
        assert manager.cache_duration == 600
        assert manager.query_timeout == 45.0
        assert manager._cache == {}

    def test_sd_card_manager_cache_expiry(self, sd_card_manager):
        """Test that cache entries expire after cache_duration"""
        from nvr.core.sd_card_manager import CachedRecordings
        import time

        camera_id = "test_camera"
        start_time = datetime.now() - timedelta(hours=1)
        end_time = datetime.now()

        # Add entry to cache with old timestamp (expired)
        sd_card_manager._cache[camera_id] = CachedRecordings(
            recordings=[{'token': 'rec1'}],
            cached_at=time.time() - 400,  # 400 seconds ago (> 300 cache_duration)
            start_time=start_time,
            end_time=end_time
        )

        # Check if cache is considered invalid (expired)
        is_valid = sd_card_manager._is_cache_valid(camera_id, start_time, end_time)
        assert is_valid is False

    def test_sd_card_manager_cache_valid(self, sd_card_manager):
        """Test that recent cache entries are valid"""
        from nvr.core.sd_card_manager import CachedRecordings
        import time

        camera_id = "test_camera"
        start_time = datetime.now() - timedelta(hours=1)
        end_time = datetime.now()

        # Add entry to cache with recent timestamp
        sd_card_manager._cache[camera_id] = CachedRecordings(
            recordings=[{'token': 'rec1'}],
            cached_at=time.time() - 100,  # 100 seconds ago (< 300 cache_duration)
            start_time=start_time,
            end_time=end_time
        )

        # Check if cache is still valid
        is_valid = sd_card_manager._is_cache_valid(camera_id, start_time, end_time)
        assert is_valid is True

    def test_sd_card_manager_register_device(self, sd_card_manager):
        """Test registering an ONVIF device"""
        mock_device = Mock()
        sd_card_manager.register_onvif_device("test_cam", mock_device)

        assert "test_cam" in sd_card_manager._onvif_devices
        assert sd_card_manager._onvif_devices["test_cam"] == mock_device

    def test_sd_card_manager_unregister_device(self, sd_card_manager):
        """Test unregistering an ONVIF device"""
        mock_device = Mock()
        sd_card_manager._onvif_devices["test_cam"] = mock_device

        sd_card_manager.unregister_onvif_device("test_cam")

        assert "test_cam" not in sd_card_manager._onvif_devices

    @pytest.mark.asyncio
    async def test_get_recordings_no_device_registered(self, sd_card_manager):
        """Test getting recordings when no ONVIF device is registered"""
        start_time = datetime.now() - timedelta(hours=1)
        end_time = datetime.now()

        # No device registered, should return empty list
        result = await sd_card_manager.get_camera_sd_recordings("test_cam", start_time, end_time)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_replay_uri_no_device(self, sd_card_manager):
        """Test getting replay URI when no device registered"""
        result = await sd_card_manager.get_replay_uri("test_cam", "token123")

        assert result is None


class TestSDCardGapsEndpoint:
    """Tests for /api/playback/sd-card-gaps endpoint"""

    @pytest.fixture
    def mock_app(self):
        """Create mock FastAPI test client"""
        from fastapi.testclient import TestClient
        from nvr.web.playback_api import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_sd_card_gaps_endpoint_returns_gaps(self):
        """Test that endpoint returns gaps in local recordings"""
        from nvr.web.playback_api import find_gaps_in_segments

        # Segments with a gap in the middle
        segments = [
            {'start_time': '2026-01-27T10:00:00', 'end_time': '2026-01-27T10:30:00'},
            {'start_time': '2026-01-27T11:00:00', 'end_time': '2026-01-27T11:30:00'},
        ]

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 12, 0, 0)

        gaps = find_gaps_in_segments(segments, start_dt, end_dt)

        # Should find gap between 10:30 and 11:00, and after 11:30
        assert len(gaps) == 2
        assert gaps[0]['start_time'] == '2026-01-27T10:30:00'
        assert gaps[0]['end_time'] == '2026-01-27T11:00:00'

    def test_sd_card_gaps_endpoint_no_gaps(self):
        """Test endpoint when there are no gaps"""
        from nvr.web.playback_api import find_gaps_in_segments

        # Continuous segments
        segments = [
            {'start_time': '2026-01-27T10:00:00', 'end_time': '2026-01-27T10:30:00'},
            {'start_time': '2026-01-27T10:30:00', 'end_time': '2026-01-27T11:00:00'},
        ]

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 11, 0, 0)

        gaps = find_gaps_in_segments(segments, start_dt, end_dt)

        assert len(gaps) == 0


class TestGapDetection:
    """Tests for find_gaps_in_segments function"""

    def test_find_gaps_empty_segments(self):
        """Test gap detection with no segments (entire range is gap)"""
        from nvr.web.playback_api import find_gaps_in_segments

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 12, 0, 0)

        gaps = find_gaps_in_segments([], start_dt, end_dt)

        assert len(gaps) == 1
        assert gaps[0]['duration_seconds'] == 7200  # 2 hours

    def test_find_gaps_no_gaps(self):
        """Test gap detection with continuous coverage"""
        from nvr.web.playback_api import find_gaps_in_segments

        segments = [
            {'start_time': '2026-01-27T10:00:00', 'end_time': '2026-01-27T11:00:00'},
            {'start_time': '2026-01-27T11:00:00', 'end_time': '2026-01-27T12:00:00'},
        ]

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 12, 0, 0)

        gaps = find_gaps_in_segments(segments, start_dt, end_dt)

        assert len(gaps) == 0

    def test_find_gaps_single_gap(self):
        """Test detection of a single gap"""
        from nvr.web.playback_api import find_gaps_in_segments

        segments = [
            {'start_time': '2026-01-27T10:00:00', 'end_time': '2026-01-27T10:30:00'},
            {'start_time': '2026-01-27T11:00:00', 'end_time': '2026-01-27T12:00:00'},
        ]

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 12, 0, 0)

        gaps = find_gaps_in_segments(segments, start_dt, end_dt)

        assert len(gaps) == 1
        assert gaps[0]['start_time'] == '2026-01-27T10:30:00'
        assert gaps[0]['end_time'] == '2026-01-27T11:00:00'
        assert gaps[0]['duration_seconds'] == 1800  # 30 minutes

    def test_find_gaps_multiple_gaps(self):
        """Test detection of multiple gaps"""
        from nvr.web.playback_api import find_gaps_in_segments

        segments = [
            {'start_time': '2026-01-27T10:00:00', 'end_time': '2026-01-27T10:15:00'},
            {'start_time': '2026-01-27T10:30:00', 'end_time': '2026-01-27T10:45:00'},
            {'start_time': '2026-01-27T11:00:00', 'end_time': '2026-01-27T11:15:00'},
        ]

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 11, 30, 0)

        gaps = find_gaps_in_segments(segments, start_dt, end_dt)

        # Gaps: 10:15-10:30, 10:45-11:00, 11:15-11:30
        assert len(gaps) == 3

    def test_find_gaps_handles_none_values(self):
        """Test gap detection handles None end_time values"""
        from nvr.web.playback_api import find_gaps_in_segments

        segments = [
            {'start_time': '2026-01-27T10:00:00', 'end_time': '2026-01-27T10:30:00'},
            {'start_time': '2026-01-27T11:00:00', 'end_time': None},  # Currently recording
        ]

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 12, 0, 0)

        # Should not raise an error, should filter out None end_time
        gaps = find_gaps_in_segments(segments, start_dt, end_dt)

        # Should have gap from 10:30 to 11:00, and from 11:00 to 12:00 (since None filtered)
        assert len(gaps) >= 1

    def test_find_gaps_handles_datetime_objects(self):
        """Test gap detection handles datetime objects (not just strings)"""
        from nvr.web.playback_api import find_gaps_in_segments

        segments = [
            {
                'start_time': datetime(2026, 1, 27, 10, 0, 0),
                'end_time': datetime(2026, 1, 27, 10, 30, 0)
            },
            {
                'start_time': datetime(2026, 1, 27, 11, 0, 0),
                'end_time': datetime(2026, 1, 27, 11, 30, 0)
            },
        ]

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 12, 0, 0)

        gaps = find_gaps_in_segments(segments, start_dt, end_dt)

        assert len(gaps) == 2  # Gap between segments and at end

    def test_find_gaps_gap_at_beginning(self):
        """Test detection of gap at the beginning of range"""
        from nvr.web.playback_api import find_gaps_in_segments

        segments = [
            {'start_time': '2026-01-27T10:30:00', 'end_time': '2026-01-27T11:00:00'},
        ]

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 11, 0, 0)

        gaps = find_gaps_in_segments(segments, start_dt, end_dt)

        assert len(gaps) == 1
        assert gaps[0]['start_time'] == '2026-01-27T10:00:00'
        assert gaps[0]['end_time'] == '2026-01-27T10:30:00'

    def test_find_gaps_gap_at_end(self):
        """Test detection of gap at the end of range"""
        from nvr.web.playback_api import find_gaps_in_segments

        segments = [
            {'start_time': '2026-01-27T10:00:00', 'end_time': '2026-01-27T10:30:00'},
        ]

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 11, 0, 0)

        gaps = find_gaps_in_segments(segments, start_dt, end_dt)

        assert len(gaps) == 1
        assert gaps[0]['start_time'] == '2026-01-27T10:30:00'
        assert gaps[0]['end_time'] == '2026-01-27T11:00:00'

    def test_find_gaps_ignores_small_gaps(self):
        """Test that gaps smaller than 1 minute are ignored"""
        from nvr.web.playback_api import find_gaps_in_segments

        segments = [
            {'start_time': '2026-01-27T10:00:00', 'end_time': '2026-01-27T10:30:00'},
            {'start_time': '2026-01-27T10:30:30', 'end_time': '2026-01-27T11:00:00'},  # 30 sec gap
        ]

        start_dt = datetime(2026, 1, 27, 10, 0, 0)
        end_dt = datetime(2026, 1, 27, 11, 0, 0)

        gaps = find_gaps_in_segments(segments, start_dt, end_dt)

        # 30 second gap should be ignored (threshold is 60 seconds)
        assert len(gaps) == 0
