"""Motion detection for video streams"""

import cv2
import numpy as np
import logging
from typing import Optional, Callable, List, Tuple
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class MotionDetector:
    """Detects motion in video frames using background subtraction"""

    def __init__(
        self,
        sensitivity: int = 25,
        min_area: int = 500,
        blur_size: int = 21,
        camera_name: str = "Unknown",
        recorder=None
    ):
        """
        Initialize motion detector

        Args:
            sensitivity: Threshold for detecting changes (0-100, higher = more sensitive)
            min_area: Minimum contour area to consider as motion
            blur_size: Gaussian blur kernel size (must be odd)
            camera_name: Name of camera for logging
            recorder: RTSPRecorder instance to log events to
        """
        self.sensitivity = sensitivity
        self.min_area = min_area
        self.blur_size = blur_size if blur_size % 2 == 1 else blur_size + 1
        self.camera_name = camera_name
        self.recorder = recorder

        # Background subtractor
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=sensitivity,
            detectShadows=True
        )

        # Previous frame for comparison
        self.prev_frame: Optional[np.ndarray] = None

        # Motion state
        self.motion_detected = False
        self.last_motion_time: Optional[datetime] = None

        # Callbacks
        self.on_motion_start: Optional[Callable] = None
        self.on_motion_end: Optional[Callable] = None

    def process_frame(self, frame: np.ndarray) -> Tuple[bool, List[Tuple[int, int, int, int]]]:
        """
        Process a frame and detect motion

        Args:
            frame: BGR image frame from video stream

        Returns:
            Tuple of (motion_detected, list of bounding boxes for motion areas)
        """
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur to reduce noise
        gray = cv2.GaussianBlur(gray, (self.blur_size, self.blur_size), 0)

        # Initialize previous frame if needed
        if self.prev_frame is None:
            self.prev_frame = gray
            return False, []

        # Check if frame size changed (e.g., due to downscaling for low quality)
        if self.prev_frame.shape != gray.shape:
            logger.debug(f"Frame size changed from {self.prev_frame.shape} to {gray.shape}, resetting motion detector")
            self.prev_frame = gray
            return False, []

        # Compute absolute difference between current and previous frame
        frame_delta = cv2.absdiff(self.prev_frame, gray)

        # Apply threshold to get binary image
        threshold = cv2.threshold(frame_delta, self.sensitivity, 255, cv2.THRESH_BINARY)[1]

        # Dilate to fill in holes
        threshold = cv2.dilate(threshold, None, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(
            threshold.copy(),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        # Filter contours by area
        motion_boxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= self.min_area:
                (x, y, w, h) = cv2.boundingRect(contour)
                motion_boxes.append((x, y, w, h))

        # Update previous frame
        self.prev_frame = gray

        # Determine if motion detected
        has_motion = len(motion_boxes) > 0

        # Handle motion state changes
        if has_motion and not self.motion_detected:
            self._on_motion_started()
        elif not has_motion and self.motion_detected:
            self._on_motion_stopped()

        # Log motion frames continuously while motion is happening
        if has_motion and self.recorder:
            self.recorder.log_motion_event()

        self.motion_detected = has_motion
        if has_motion:
            self.last_motion_time = datetime.now()

        return has_motion, motion_boxes

    def _on_motion_started(self) -> None:
        """Called when motion starts"""
        logger.info(f"Motion detected on {self.camera_name}")

        # Log to recorder/database
        if self.recorder:
            self.recorder.log_motion_event()

        if self.on_motion_start:
            try:
                self.on_motion_start()
            except Exception as e:
                logger.error(f"Error in motion start callback: {e}")

    def _on_motion_stopped(self) -> None:
        """Called when motion stops"""
        logger.info(f"Motion ended on {self.camera_name}")

        # End motion event in recorder/database
        if self.recorder:
            self.recorder.end_motion_event()

        if self.on_motion_end:
            try:
                self.on_motion_end()
            except Exception as e:
                logger.error(f"Error in motion end callback: {e}")

    def draw_motion(
        self,
        frame: np.ndarray,
        motion_boxes: List[Tuple[int, int, int, int]]
    ) -> np.ndarray:
        """
        Draw bounding boxes around motion areas

        Args:
            frame: Original BGR frame
            motion_boxes: List of bounding boxes

        Returns:
            Frame with motion boxes drawn
        """
        result = frame.copy()

        for (x, y, w, h) in motion_boxes:
            cv2.rectangle(result, (x, y), (x + w, y + h), (0, 255, 0), 2)

        # Add motion indicator text
        if motion_boxes:
            cv2.putText(
                result,
                "MOTION DETECTED",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 0, 255),
                2
            )

        return result

    def reset(self) -> None:
        """Reset motion detector state"""
        self.prev_frame = None
        self.motion_detected = False
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=self.sensitivity,
            detectShadows=True
        )


class MotionMonitor:
    """Monitors motion detection across multiple cameras"""

    def __init__(self):
        self.detectors: dict[str, MotionDetector] = {}
        self.is_running = False

    def add_camera(
        self,
        camera_name: str,
        sensitivity: int = 25,
        min_area: int = 500,
        recorder=None
    ) -> MotionDetector:
        """Add a camera to motion monitoring"""
        if camera_name in self.detectors:
            logger.warning(f"Motion detector for {camera_name} already exists")
            return self.detectors[camera_name]

        detector = MotionDetector(
            sensitivity=sensitivity,
            min_area=min_area,
            camera_name=camera_name,
            recorder=recorder
        )

        self.detectors[camera_name] = detector
        logger.info(f"Added motion detector for {camera_name}")

        return detector

    def remove_camera(self, camera_name: str) -> bool:
        """Remove a camera from motion monitoring"""
        if camera_name in self.detectors:
            del self.detectors[camera_name]
            logger.info(f"Removed motion detector for {camera_name}")
            return True
        return False

    def get_detector(self, camera_name: str) -> Optional[MotionDetector]:
        """Get motion detector for a camera"""
        return self.detectors.get(camera_name)

    async def monitor_recorder(
        self,
        camera_name: str,
        recorder,
        check_interval: int = 1
    ) -> None:
        """
        Monitor motion from a recorder's frame queue

        Args:
            camera_name: Camera name
            recorder: RTSPRecorder instance
            check_interval: Frames to skip between checks
        """
        detector = self.get_detector(camera_name)
        if not detector:
            logger.error(f"No motion detector for {camera_name}")
            return

        frame_count = 0

        while self.is_running:
            try:
                # Get latest frame from recorder (JPEG bytes)
                jpeg_data = recorder.get_latest_frame()

                if jpeg_data is not None:
                    # Decode JPEG bytes to numpy array for motion detection
                    nparr = np.frombuffer(jpeg_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    if frame is not None:
                        frame_count += 1

                        # Only check every Nth frame to reduce CPU
                        if frame_count % check_interval == 0:
                            has_motion, boxes = detector.process_frame(frame)

                            if has_motion:
                                logger.debug(
                                    f"Motion on {camera_name}: "
                                    f"{len(boxes)} area(s) detected"
                                )

                await asyncio.sleep(0.01)  # Small delay to prevent busy loop

            except Exception as e:
                logger.error(f"Error monitoring motion for {camera_name}: {e}")
                await asyncio.sleep(1)

    async def start_monitoring(self, recorder_manager) -> None:
        """Start monitoring all cameras"""
        self.is_running = True

        tasks = []
        for camera_name, recorder in recorder_manager.recorders.items():
            if camera_name in self.detectors:
                task = asyncio.create_task(
                    self.monitor_recorder(camera_name, recorder)
                )
                tasks.append(task)

        if tasks:
            logger.info(f"Started motion monitoring for {len(tasks)} camera(s)")
            await asyncio.gather(*tasks)

    def stop_monitoring(self) -> None:
        """Stop monitoring all cameras"""
        self.is_running = False
        logger.info("Stopped motion monitoring")