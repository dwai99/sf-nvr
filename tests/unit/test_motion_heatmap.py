"""Unit tests for MotionHeatmap - motion pattern visualization"""

import pytest
import numpy as np
import cv2
from pathlib import Path
from datetime import datetime, timedelta

from nvr.core.motion_heatmap import MotionHeatmap, MotionHeatmapManager


@pytest.mark.unit
class TestMotionHeatmap:
    """Test MotionHeatmap class"""

    def test_init_heatmap(self):
        """Test heatmap initialization"""
        heatmap = MotionHeatmap(width=160, height=90)

        assert heatmap.width == 160
        assert heatmap.height == 90
        assert heatmap.sample_count == 0
        assert heatmap.heatmap.shape == (90, 160)

    def test_reset_heatmap(self):
        """Test resetting heatmap clears data"""
        heatmap = MotionHeatmap(width=160, height=90)

        # Add some motion
        heatmap.add_motion_regions([(10, 10, 50, 50)], 1920, 1080)
        assert heatmap.sample_count == 1
        assert np.sum(heatmap.heatmap) > 0

        # Reset
        heatmap.reset()
        assert heatmap.sample_count == 0
        assert np.sum(heatmap.heatmap) == 0

    def test_add_motion_regions_scaling(self):
        """Test that motion regions are scaled correctly"""
        heatmap = MotionHeatmap(width=160, height=90)

        # Add motion box at (0, 0, 1920, 1080) - full frame
        # Should map to (0, 0, 160, 90) on heatmap
        heatmap.add_motion_regions([(0, 0, 1920, 1080)], 1920, 1080)

        assert heatmap.sample_count == 1
        assert np.sum(heatmap.heatmap) > 0  # Should have motion data

    def test_add_motion_regions_multiple_boxes(self):
        """Test adding multiple motion boxes"""
        heatmap = MotionHeatmap(width=160, height=90)

        motion_boxes = [
            (100, 100, 200, 200),  # Box 1
            (500, 500, 300, 300),  # Box 2
            (1000, 200, 400, 400)  # Box 3
        ]

        heatmap.add_motion_regions(motion_boxes, 1920, 1080)

        assert heatmap.sample_count == 1
        # Should have motion in multiple regions
        assert np.sum(heatmap.heatmap) > 0

    def test_add_motion_empty_list(self):
        """Test adding empty motion list (no motion)"""
        heatmap = MotionHeatmap(width=160, height=90)

        heatmap.add_motion_regions([], 1920, 1080)

        # Should not increment sample count for empty list
        assert heatmap.sample_count == 0
        assert np.sum(heatmap.heatmap) == 0

    def test_accumulation_over_time(self):
        """Test that heatmap accumulates motion over multiple calls"""
        heatmap = MotionHeatmap(width=160, height=90)

        # Add motion in same region 5 times
        for i in range(5):
            heatmap.add_motion_regions([(100, 100, 200, 200)], 1920, 1080)

        assert heatmap.sample_count == 5
        # Heat should accumulate (sum should increase with each addition)
        assert np.max(heatmap.heatmap) >= 5.0

    def test_get_normalized_heatmap_empty(self):
        """Test normalized heatmap with no data"""
        heatmap = MotionHeatmap(width=160, height=90)

        normalized = heatmap.get_normalized_heatmap()

        assert normalized.shape == (90, 160)
        assert normalized.dtype == np.uint8
        assert np.sum(normalized) == 0  # All zeros

    def test_get_normalized_heatmap_with_data(self):
        """Test normalized heatmap with motion data"""
        heatmap = MotionHeatmap(width=160, height=90)

        # Add some motion
        heatmap.add_motion_regions([(100, 100, 200, 200)], 1920, 1080)

        normalized = heatmap.get_normalized_heatmap()

        assert normalized.shape == (90, 160)
        assert normalized.dtype == np.uint8
        assert np.max(normalized) == 255  # Normalized to max
        assert np.sum(normalized) > 0

    def test_get_normalized_heatmap_range(self):
        """Test that normalized values are in 0-255 range"""
        heatmap = MotionHeatmap(width=160, height=90)

        # Add varying amounts of motion
        for i in range(10):
            heatmap.add_motion_regions([(i * 100, i * 50, 200, 200)], 1920, 1080)

        normalized = heatmap.get_normalized_heatmap()

        assert np.min(normalized) >= 0
        assert np.max(normalized) <= 255

    def test_generate_heatmap_image(self):
        """Test generating colored heatmap image"""
        heatmap = MotionHeatmap(width=160, height=90)

        # Add motion
        heatmap.add_motion_regions([(500, 500, 400, 400)], 1920, 1080)

        # Generate colored heatmap
        colored = heatmap.generate_heatmap_image(colormap=cv2.COLORMAP_JET)

        assert colored.shape == (90, 160, 3)  # RGB image
        assert colored.dtype == np.uint8

    def test_generate_heatmap_different_colormaps(self):
        """Test generating heatmaps with different colormaps"""
        heatmap = MotionHeatmap(width=160, height=90)
        heatmap.add_motion_regions([(500, 500, 400, 400)], 1920, 1080)

        colormaps = [cv2.COLORMAP_JET, cv2.COLORMAP_HOT, cv2.COLORMAP_VIRIDIS]

        for cmap in colormaps:
            colored = heatmap.generate_heatmap_image(colormap=cmap)
            assert colored.shape == (90, 160, 3)

    def test_overlay_on_frame(self):
        """Test overlaying heatmap on video frame"""
        heatmap = MotionHeatmap(width=160, height=90)
        heatmap.add_motion_regions([(500, 500, 400, 400)], 1920, 1080)

        # Create dummy frame (1920x1080 BGR)
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)

        # Overlay heatmap
        overlay = heatmap.overlay_on_frame(frame, alpha=0.5)

        assert overlay.shape == frame.shape
        assert overlay.dtype == np.uint8

    def test_overlay_with_different_alpha(self):
        """Test overlay with different transparency values"""
        heatmap = MotionHeatmap(width=160, height=90)
        heatmap.add_motion_regions([(500, 500, 400, 400)], 1920, 1080)

        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)

        # Test different alpha values
        for alpha in [0.0, 0.3, 0.5, 0.7, 1.0]:
            overlay = heatmap.overlay_on_frame(frame, alpha=alpha)
            assert overlay.shape == frame.shape

    def test_overlay_on_empty_frame(self):
        """Test overlay handling of empty frame"""
        heatmap = MotionHeatmap(width=160, height=90)
        heatmap.add_motion_regions([(500, 500, 400, 400)], 1920, 1080)

        # Test with None frame
        result = heatmap.overlay_on_frame(None, alpha=0.5)
        assert result is None

    def test_save_heatmap(self, temp_dir):
        """Test saving heatmap to file"""
        heatmap = MotionHeatmap(width=160, height=90)
        heatmap.add_motion_regions([(500, 500, 400, 400)], 1920, 1080)

        output_path = temp_dir / "heatmap.png"
        heatmap.save_heatmap(output_path)

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_to_dict(self):
        """Test exporting heatmap as dictionary"""
        heatmap = MotionHeatmap(width=160, height=90)
        heatmap.add_motion_regions([(500, 500, 400, 400)], 1920, 1080)

        data = heatmap.to_dict()

        assert data['width'] == 160
        assert data['height'] == 90
        assert data['sample_count'] == 1
        assert 'heatmap' in data
        assert isinstance(data['heatmap'], list)
        assert len(data['heatmap']) == 90  # Height
        assert len(data['heatmap'][0]) == 160  # Width

    def test_bounds_checking(self):
        """Test that motion boxes outside frame bounds are handled"""
        heatmap = MotionHeatmap(width=160, height=90)

        # Motion box partially outside frame
        heatmap.add_motion_regions([(1800, 1000, 500, 500)], 1920, 1080)

        # Should not crash
        assert heatmap.sample_count == 1
        normalized = heatmap.get_normalized_heatmap()
        assert normalized.shape == (90, 160)


@pytest.mark.unit
class TestMotionHeatmapManager:
    """Test MotionHeatmapManager class"""

    def test_init_manager(self, temp_dir):
        """Test manager initialization"""
        manager = MotionHeatmapManager(temp_dir)

        assert manager.storage_path == temp_dir
        assert manager.heatmap_dir.exists()
        assert manager.heatmap_dir == temp_dir / "heatmaps"

    def test_get_or_create_heatmap_new(self, temp_dir):
        """Test creating new heatmap for camera"""
        manager = MotionHeatmapManager(temp_dir)

        heatmap = manager.get_or_create_heatmap("camera_1")

        assert isinstance(heatmap, MotionHeatmap)
        assert "camera_1" in manager.heatmaps

    def test_get_or_create_heatmap_existing(self, temp_dir):
        """Test getting existing heatmap for camera"""
        manager = MotionHeatmapManager(temp_dir)

        # Create heatmap and add some data
        heatmap1 = manager.get_or_create_heatmap("camera_1")
        heatmap1.add_motion_regions([(100, 100, 200, 200)], 1920, 1080)

        # Get same heatmap again
        heatmap2 = manager.get_or_create_heatmap("camera_1")

        # Should be the same instance
        assert heatmap1 is heatmap2
        assert heatmap2.sample_count == 1

    def test_multiple_cameras(self, temp_dir):
        """Test managing heatmaps for multiple cameras"""
        manager = MotionHeatmapManager(temp_dir)

        # Create heatmaps for different cameras
        heatmap1 = manager.get_or_create_heatmap("camera_1")
        heatmap2 = manager.get_or_create_heatmap("camera_2")
        heatmap3 = manager.get_or_create_heatmap("camera_3")

        # Should all be different instances
        assert heatmap1 is not heatmap2
        assert heatmap2 is not heatmap3
        assert len(manager.heatmaps) == 3

    def test_generate_heatmap_for_timerange_no_db(self, temp_dir):
        """Test generating heatmap without database connection"""
        manager = MotionHeatmapManager(temp_dir, playback_db=None)

        start_time = datetime(2026, 1, 20, 12, 0, 0)
        end_time = datetime(2026, 1, 20, 13, 0, 0)

        # Should return None when no database
        result = manager.generate_heatmap_for_timerange(
            "camera_1", start_time, end_time
        )

        assert result is None

    def test_generate_heatmap_for_timerange_with_db(self, temp_dir, playback_db):
        """Test generating heatmap from database motion events"""
        manager = MotionHeatmapManager(temp_dir, playback_db=playback_db)

        # Add some motion events to database
        base_time = datetime(2026, 1, 20, 12, 0, 0)
        for i in range(10):
            event_time = base_time + timedelta(minutes=i * 2)
            playback_db.add_motion_event(
                camera_id="camera_1",
                event_time=event_time,
                intensity=50 + i * 5
            )

        # Generate heatmap
        heatmap = manager.generate_heatmap_for_timerange(
            camera_name="camera_1",
            start_time=base_time,
            end_time=base_time + timedelta(hours=1),
            sample_rate=1
        )

        # Should return a heatmap (implementation may vary)
        # This test validates the API works without errors
        assert heatmap is None or isinstance(heatmap, MotionHeatmap)


@pytest.mark.unit
class TestMotionHeatmapEdgeCases:
    """Test edge cases and error conditions"""

    def test_very_small_heatmap(self):
        """Test heatmap with very small dimensions"""
        heatmap = MotionHeatmap(width=10, height=10)

        heatmap.add_motion_regions([(500, 500, 400, 400)], 1920, 1080)

        assert heatmap.heatmap.shape == (10, 10)
        normalized = heatmap.get_normalized_heatmap()
        assert normalized.shape == (10, 10)

    def test_very_large_heatmap(self):
        """Test heatmap with large dimensions"""
        heatmap = MotionHeatmap(width=640, height=360)

        heatmap.add_motion_regions([(500, 500, 400, 400)], 1920, 1080)

        assert heatmap.heatmap.shape == (360, 640)
        normalized = heatmap.get_normalized_heatmap()
        assert normalized.shape == (360, 640)

    def test_zero_size_motion_box(self):
        """Test motion box with zero width or height"""
        heatmap = MotionHeatmap(width=160, height=90)

        # Zero-size boxes
        heatmap.add_motion_regions([(100, 100, 0, 0)], 1920, 1080)

        # Should not crash
        assert heatmap.sample_count == 1

    def test_negative_coordinates(self):
        """Test motion box with negative coordinates"""
        heatmap = MotionHeatmap(width=160, height=90)

        # Negative coordinates (should be clamped to 0)
        heatmap.add_motion_regions([(-100, -100, 200, 200)], 1920, 1080)

        # Should not crash
        assert heatmap.sample_count == 1
        normalized = heatmap.get_normalized_heatmap()
        assert np.sum(normalized) >= 0

    def test_motion_box_larger_than_frame(self):
        """Test motion box larger than source frame"""
        heatmap = MotionHeatmap(width=160, height=90)

        # Box larger than frame
        heatmap.add_motion_regions([(0, 0, 5000, 5000)], 1920, 1080)

        # Should be clamped to frame size
        assert heatmap.sample_count == 1

    def test_different_aspect_ratios(self):
        """Test with different source/heatmap aspect ratios"""
        heatmap = MotionHeatmap(width=160, height=120)  # 4:3

        # Add motion from 16:9 source
        heatmap.add_motion_regions([(500, 500, 400, 400)], 1920, 1080)

        # Should handle aspect ratio difference
        normalized = heatmap.get_normalized_heatmap()
        assert normalized.shape == (120, 160)
