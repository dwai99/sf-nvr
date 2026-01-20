"""Motion heatmap generator for visualizing motion patterns"""

import logging
import numpy as np
import cv2
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json

logger = logging.getLogger(__name__)


class MotionHeatmap:
    """Generates heatmaps showing motion patterns over time"""

    def __init__(self, width: int = 160, height: int = 90):
        """
        Initialize motion heatmap

        Args:
            width: Heatmap width in pixels (low res for efficiency)
            height: Heatmap height in pixels
        """
        self.width = width
        self.height = height
        self.reset()

    def reset(self):
        """Reset the heatmap"""
        self.heatmap = np.zeros((self.height, self.width), dtype=np.float32)
        self.sample_count = 0

    def add_motion_regions(self, motion_boxes: List[Tuple[int, int, int, int]], source_width: int, source_height: int):
        """
        Add motion regions to the heatmap

        Args:
            motion_boxes: List of (x, y, w, h) tuples for motion regions
            source_width: Original frame width
            source_height: Original frame height
        """
        if not motion_boxes:
            return

        # Scale factors
        scale_x = self.width / source_width
        scale_y = self.height / source_height

        # Create temporary motion mask
        motion_mask = np.zeros((self.height, self.width), dtype=np.float32)

        for (x, y, w, h) in motion_boxes:
            # Scale coordinates to heatmap size
            hm_x1 = int(x * scale_x)
            hm_y1 = int(y * scale_y)
            hm_x2 = int((x + w) * scale_x)
            hm_y2 = int((y + h) * scale_y)

            # Bounds check
            hm_x1 = max(0, min(hm_x1, self.width - 1))
            hm_y1 = max(0, min(hm_y1, self.height - 1))
            hm_x2 = max(0, min(hm_x2, self.width))
            hm_y2 = max(0, min(hm_y2, self.height))

            # Add motion region to mask
            motion_mask[hm_y1:hm_y2, hm_x1:hm_x2] += 1.0

        # Accumulate into heatmap
        self.heatmap += motion_mask
        self.sample_count += 1

    def get_normalized_heatmap(self) -> np.ndarray:
        """
        Get normalized heatmap (0-255 intensity)

        Returns:
            Numpy array with heatmap data
        """
        if self.sample_count == 0:
            return np.zeros((self.height, self.width), dtype=np.uint8)

        # Normalize to 0-1 range
        max_val = np.max(self.heatmap)
        if max_val > 0:
            normalized = self.heatmap / max_val
        else:
            normalized = self.heatmap

        # Convert to 0-255
        return (normalized * 255).astype(np.uint8)

    def generate_heatmap_image(self, colormap: int = cv2.COLORMAP_JET) -> np.ndarray:
        """
        Generate a colored heatmap image

        Args:
            colormap: OpenCV colormap to use

        Returns:
            RGB image of heatmap
        """
        heatmap_gray = self.get_normalized_heatmap()

        # Apply colormap
        heatmap_colored = cv2.applyColorMap(heatmap_gray, colormap)

        # Convert BGR to RGB
        heatmap_rgb = cv2.cvtColor(heatmap_colored, cv2.COLOR_BGR2RGB)

        return heatmap_rgb

    def overlay_on_frame(self, frame: np.ndarray, alpha: float = 0.5) -> np.ndarray:
        """
        Overlay heatmap on a video frame

        Args:
            frame: Original video frame (BGR)
            alpha: Heatmap transparency (0=invisible, 1=opaque)

        Returns:
            Frame with heatmap overlay
        """
        if frame is None or frame.size == 0:
            return frame

        # Get heatmap
        heatmap = self.generate_heatmap_image()

        # Resize heatmap to match frame size
        heatmap_resized = cv2.resize(
            heatmap,
            (frame.shape[1], frame.shape[0]),
            interpolation=cv2.INTER_LINEAR
        )

        # Convert heatmap RGB to BGR for OpenCV
        heatmap_bgr = cv2.cvtColor(heatmap_resized, cv2.COLOR_RGB2BGR)

        # Blend with original frame
        overlay = cv2.addWeighted(frame, 1 - alpha, heatmap_bgr, alpha, 0)

        return overlay

    def save_heatmap(self, output_path: Path):
        """
        Save heatmap to file

        Args:
            output_path: Path to save image
        """
        heatmap_img = self.generate_heatmap_image()
        cv2.imwrite(str(output_path), cv2.cvtColor(heatmap_img, cv2.COLOR_RGB2BGR))
        logger.info(f"Saved heatmap to {output_path}")

    def to_dict(self) -> Dict:
        """Export heatmap data as dictionary"""
        return {
            'width': self.width,
            'height': self.height,
            'sample_count': self.sample_count,
            'heatmap': self.get_normalized_heatmap().tolist()
        }


class MotionHeatmapManager:
    """Manages heatmaps for multiple cameras"""

    def __init__(self, storage_path: Path, playback_db=None):
        self.storage_path = Path(storage_path)
        self.playback_db = playback_db
        self.heatmaps: Dict[str, MotionHeatmap] = {}
        self.heatmap_dir = self.storage_path / "heatmaps"
        self.heatmap_dir.mkdir(exist_ok=True)

    def get_or_create_heatmap(self, camera_name: str) -> MotionHeatmap:
        """Get existing heatmap or create new one for camera"""
        if camera_name not in self.heatmaps:
            self.heatmaps[camera_name] = MotionHeatmap()
        return self.heatmaps[camera_name]

    def generate_heatmap_for_timerange(
        self,
        camera_name: str,
        start_time: datetime,
        end_time: datetime,
        sample_rate: int = 30
    ) -> Optional[MotionHeatmap]:
        """
        Generate heatmap from motion events in database

        Args:
            camera_name: Name of camera
            start_time: Start of time range
            end_time: End of time range
            sample_rate: Sample every Nth motion event (for performance)

        Returns:
            MotionHeatmap or None if no data
        """
        if not self.playback_db:
            logger.warning("No playback database available for heatmap generation")
            return None

        try:
            # Get motion events from database
            events = self.playback_db.get_motion_events_in_range(
                camera_name,
                start_time,
                end_time
            )

            if not events:
                logger.info(f"No motion events found for {camera_name} in specified range")
                return None

            # Create new heatmap
            heatmap = MotionHeatmap()

            # Assume 1920x1080 resolution (adjust if needed)
            source_width = 1920
            source_height = 1080

            # Sample events for performance
            sampled_events = events[::sample_rate] if len(events) > sample_rate else events

            logger.info(f"Generating heatmap from {len(sampled_events)} motion events (of {len(events)} total)")

            # Process each event
            for event in sampled_events:
                # Motion events store intensity but not bounding boxes
                # For now, we'll create a simple approximation
                # In a future enhancement, store actual bounding boxes in motion events

                # Generate a small region in center (placeholder)
                # This should be replaced with actual motion region data
                center_box = (
                    source_width // 2 - 100,
                    source_height // 2 - 100,
                    200,
                    200
                )
                heatmap.add_motion_regions([center_box], source_width, source_height)

            return heatmap

        except Exception as e:
            logger.error(f"Error generating heatmap: {e}")
            return None

    def generate_and_save_heatmap(
        self,
        camera_name: str,
        start_time: datetime,
        end_time: datetime
    ) -> Optional[Path]:
        """
        Generate heatmap and save to file

        Returns:
            Path to saved heatmap image, or None if failed
        """
        heatmap = self.generate_heatmap_for_timerange(camera_name, start_time, end_time)

        if not heatmap:
            return None

        # Create filename
        date_str = start_time.strftime("%Y%m%d")
        time_str = start_time.strftime("%H%M")
        filename = f"{camera_name}_{date_str}_{time_str}_heatmap.png"
        output_path = self.heatmap_dir / filename

        heatmap.save_heatmap(output_path)
        return output_path

    def get_daily_heatmap(self, camera_name: str, date: datetime) -> Optional[Path]:
        """
        Get or generate daily heatmap for a camera

        Args:
            camera_name: Name of camera
            date: Date to generate heatmap for

        Returns:
            Path to heatmap image
        """
        # Check if heatmap already exists
        date_str = date.strftime("%Y%m%d")
        filename = f"{camera_name}_{date_str}_daily_heatmap.png"
        heatmap_path = self.heatmap_dir / filename

        if heatmap_path.exists():
            return heatmap_path

        # Generate new heatmap
        start_time = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(days=1)

        return self.generate_and_save_heatmap(camera_name, start_time, end_time)
