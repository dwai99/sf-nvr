"""Motion detection for video streams"""

import cv2
import numpy as np
import logging
import threading
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
        recorder=None,
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

        # Previous frame for comparison
        self.prev_frame: Optional[np.ndarray] = None

        # Serializes process_frame: the detector is shared between the motion
        # monitor (now a worker thread) and the live-view overlay.
        self._lock = threading.Lock()

        # Motion state
        self.motion_detected = False
        self.last_motion_time: Optional[datetime] = None

        # Latest detection result, cached so the live-view overlay can reuse it
        # instead of re-running detection per viewer. Boxes are in the processed
        # frame's full-resolution pixel space.
        self.last_boxes: List[Tuple[int, int, int, int]] = []
        self.last_has_motion = False

        # Callbacks
        self.on_motion_start: Optional[Callable] = None
        self.on_motion_end: Optional[Callable] = None

    def process_frame(self, frame: np.ndarray) -> Tuple[bool, List[Tuple[int, int, int, int]]]:
        """Process a frame and detect motion (thread-safe wrapper).

        Serializes access to prev_frame/state because the detector is shared
        between the motion-monitor thread and the live-view overlay.
        """
        with self._lock:
            return self._process_frame_impl(frame)

    def _process_frame_impl(self, frame: np.ndarray) -> Tuple[bool, List[Tuple[int, int, int, int]]]:
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
        contours, _ = cv2.findContours(threshold.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours by area
        motion_boxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= self.min_area:
                (x, y, w, h) = cv2.boundingRect(contour)
                motion_boxes.append((x, y, w, h))

        # Update previous frame
        self.prev_frame = gray

        # Determine if motion detected in this frame
        has_motion = len(motion_boxes) > 0
        now = datetime.now()

        # Cooldown period: don't end motion event until no motion for this many seconds
        # This prevents rapid start/stop cycles from creating many tiny events
        MOTION_COOLDOWN_SECONDS = 3.0

        # Handle motion state changes with cooldown
        if has_motion:
            # Motion detected - start event if not already in one
            if not self.motion_detected:
                self._on_motion_started()
            self.last_motion_time = now
            self.motion_detected = True
        else:
            # No motion in this frame - check cooldown before ending event
            if self.motion_detected and self.last_motion_time:
                time_since_motion = (now - self.last_motion_time).total_seconds()
                # A DST/NTP backward step makes this negative; treat that as the
                # cooldown having elapsed so a motion event can't hang forever.
                if time_since_motion < 0:
                    time_since_motion = MOTION_COOLDOWN_SECONDS
                if time_since_motion >= MOTION_COOLDOWN_SECONDS:
                    # Cooldown expired, end the motion event
                    self._on_motion_stopped()
                    self.motion_detected = False

        # Log motion frames continuously while in motion state
        if self.motion_detected and self.recorder:
            self.recorder.log_motion_event()

        # Update recorder's motion state for recording mode decisions
        if self.recorder and hasattr(self.recorder, "update_motion_state"):
            self.recorder.update_motion_state(self.motion_detected)

        # Cache for the live-view overlay to reuse without reprocessing.
        self.last_boxes = motion_boxes
        self.last_has_motion = has_motion

        return has_motion, motion_boxes

    def get_last_motion(self) -> Tuple[bool, List[Tuple[int, int, int, int]]]:
        """Return the most recent (has_motion, boxes) without reprocessing.

        Lets the live-view overlay reuse the motion monitor's latest result
        instead of running detection again per viewer. Boxes are in the
        full-resolution frame's pixel space.
        """
        with self._lock:
            return self.last_has_motion, list(self.last_boxes)

    def _on_motion_started(self) -> None:
        """Called when motion starts"""
        logger.debug(f"Motion detected on {self.camera_name}")

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
        logger.debug(f"Motion ended on {self.camera_name}")

        # End motion event in recorder/database
        if self.recorder:
            self.recorder.end_motion_event()

        if self.on_motion_end:
            try:
                self.on_motion_end()
            except Exception as e:
                logger.error(f"Error in motion end callback: {e}")

    def draw_motion(self, frame: np.ndarray, motion_boxes: List[Tuple[int, int, int, int]]) -> np.ndarray:
        """
        Draw bounding boxes around motion areas

        Args:
            frame: Original BGR frame
            motion_boxes: List of bounding boxes

        Returns:
            Frame with motion boxes drawn
        """
        result = frame.copy()

        for x, y, w, h in motion_boxes:
            cv2.rectangle(result, (x, y), (x + w, y + h), (0, 255, 0), 2)

        # Add motion indicator text
        if motion_boxes:
            cv2.putText(result, "MOTION DETECTED", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        return result

    def reset(self) -> None:
        """Reset motion detector state"""
        self.prev_frame = None
        self.motion_detected = False


class MotionMonitor:
    """Monitors motion detection across multiple cameras"""

    def __init__(self):
        self.detectors: dict[str, MotionDetector] = {}
        self.is_running = False

    def add_camera(self, camera_name: str, sensitivity: int = 25, min_area: int = 500, recorder=None) -> MotionDetector:
        """Add a camera to motion monitoring"""
        if camera_name in self.detectors:
            logger.warning(f"Motion detector for {camera_name} already exists")
            return self.detectors[camera_name]

        detector = MotionDetector(
            sensitivity=sensitivity, min_area=min_area, camera_name=camera_name, recorder=recorder
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

    # How often each camera's motion is sampled. A few checks/sec is ample for
    # motion detection and keeps CPU/event-loop load low.
    POLL_INTERVAL_SECONDS = 0.2

    async def monitor_recorder(
        self,
        camera_name: str,
        recorder,
        check_interval: int = 1,  # deprecated/unused: we now skip unchanged frames
    ) -> None:
        """
        Monitor motion from a recorder's latest frame.

        The heavy work (JPEG decode + contour detection) runs in a worker thread
        via asyncio.to_thread so it never blocks the event loop, and we skip
        frames we've already processed (get_latest_frame returns the cached frame
        when no new one has arrived), avoiding redundant CPU on every tick.
        """
        detector = self.get_detector(camera_name)
        if not detector:
            logger.error(f"No motion detector for {camera_name}")
            return

        last_processed = None  # identity of the last JPEG buffer we ran detection on

        def _decode_and_process(jpeg_bytes):
            # Runs off the event loop
            nparr = np.frombuffer(jpeg_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is None:
                return None
            return detector.process_frame(frame)

        while self.is_running:
            try:
                jpeg_data = recorder.get_latest_frame()

                # Only process genuinely new frames (get_latest_frame returns the
                # same cached object when the queue is empty).
                if jpeg_data is not None and jpeg_data is not last_processed:
                    last_processed = jpeg_data
                    result = await asyncio.to_thread(_decode_and_process, jpeg_data)
                    if result:
                        has_motion, boxes = result
                        if has_motion:
                            logger.debug(f"Motion on {camera_name}: {len(boxes)} area(s) detected")

                await asyncio.sleep(self.POLL_INTERVAL_SECONDS)

            except Exception as e:
                logger.error(f"Error monitoring motion for {camera_name}: {e}")
                await asyncio.sleep(1)

    async def start_monitoring(self, recorder_manager) -> None:
        """Start monitoring all cameras"""
        self.is_running = True

        tasks = []
        for camera_name, recorder in recorder_manager.recorders.items():
            if camera_name in self.detectors:
                task = asyncio.create_task(self.monitor_recorder(camera_name, recorder))
                tasks.append(task)

        if tasks:
            logger.info(f"Started motion monitoring for {len(tasks)} camera(s)")
            await asyncio.gather(*tasks)

    def stop_monitoring(self) -> None:
        """Stop monitoring all cameras"""
        self.is_running = False
        logger.info("Stopped motion monitoring")
