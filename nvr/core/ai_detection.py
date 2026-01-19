"""AI-based object detection for person and vehicle recognition"""

import cv2
import numpy as np
import logging
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime
import urllib.request

logger = logging.getLogger(__name__)


class AIObjectDetector:
    """
    Detects people and vehicles using OpenCV DNN with pre-trained models.
    Uses MobileNet-SSD for efficiency (good for real-time on CPU).
    """

    # COCO class labels for MobileNet-SSD
    CLASSES = [
        "background", "aeroplane", "bicycle", "bird", "boat",
        "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
        "dog", "horse", "motorbike", "person", "pottedplant", "sheep",
        "sofa", "train", "tvmonitor"
    ]

    # Classes we care about for bar security
    PERSON_CLASS = "person"
    VEHICLE_CLASSES = {"car", "bus", "motorbike", "bicycle"}

    def __init__(
        self,
        model_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
        confidence_threshold: float = 0.5,
        camera_name: str = "Unknown",
        recorder=None
    ):
        """
        Initialize AI object detector

        Args:
            model_path: Path to model weights (will auto-download if not provided)
            config_path: Path to model config (will auto-download if not provided)
            confidence_threshold: Minimum confidence for detection (0.0-1.0)
            camera_name: Name of camera for logging
            recorder: RTSPRecorder instance to log events to
        """
        self.confidence_threshold = confidence_threshold
        self.camera_name = camera_name
        self.recorder = recorder

        # Detection state
        self.person_detected = False
        self.vehicle_detected = False
        self.last_person_time: Optional[datetime] = None
        self.last_vehicle_time: Optional[datetime] = None

        # Event tracking
        self.current_event_type: Optional[str] = None
        self.event_start_time: Optional[datetime] = None
        self.event_frame_count: int = 0

        # Initialize model
        self.net = self._load_model(model_path, config_path)
        logger.info(f"AI detector initialized for {camera_name}")

    def _load_model(
        self,
        model_path: Optional[Path],
        config_path: Optional[Path]
    ) -> cv2.dnn.Net:
        """Load or download the MobileNet-SSD model"""
        models_dir = Path("models")
        models_dir.mkdir(exist_ok=True)

        # Use provided paths or defaults
        if model_path is None:
            model_path = models_dir / "MobileNetSSD_deploy.caffemodel"
        if config_path is None:
            config_path = models_dir / "MobileNetSSD_deploy.prototxt"

        # Download model if not present
        if not model_path.exists() or not config_path.exists():
            logger.info("Downloading MobileNet-SSD model (one-time setup)...")
            self._download_model(model_path, config_path)

        # Load model
        try:
            net = cv2.dnn.readNetFromCaffe(
                str(config_path),
                str(model_path)
            )

            # Use CPU by default (can add GPU support later)
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

            logger.info("Model loaded successfully")
            return net

        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise

    def _download_model(self, model_path: Path, config_path: Path):
        """Download MobileNet-SSD model files"""
        # Use OpenCV's DNN samples repository which has stable URLs
        prototxt_url = "https://github.com/opencv/opencv/raw/master/samples/dnn/face_detector/deploy.prototxt"
        model_url = "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"

        # Alternative: Use OpenCV's MobileNet-SSD from a reliable source
        prototxt_url = "https://raw.githubusercontent.com/djmv/MobilNet-SSD-opencv/master/MobileNetSSD_deploy.prototxt"
        model_url = "https://github.com/djmv/MobilNet-SSD-opencv/raw/master/MobileNetSSD_deploy.caffemodel"

        try:
            # Download prototxt
            logger.info("Downloading model config...")
            urllib.request.urlretrieve(prototxt_url, str(config_path))

            # Download caffemodel
            logger.info("Downloading model weights (23MB)...")
            urllib.request.urlretrieve(model_url, str(model_path))

            logger.info("Model download complete")

        except Exception as e:
            logger.error(f"Error downloading model: {e}")
            logger.error("Please download manually:")
            logger.error(f"  Config: {prototxt_url}")
            logger.error(f"  Model: {model_url}")
            logger.error(f"  Save to: {model_path.parent}/")
            raise

    def detect_objects(
        self,
        frame: np.ndarray
    ) -> Tuple[bool, bool, List[dict]]:
        """
        Detect people and vehicles in frame

        Args:
            frame: BGR image frame

        Returns:
            Tuple of (person_detected, vehicle_detected, detections_list)
            detections_list contains dict with: class, confidence, bbox
        """
        (h, w) = frame.shape[:2]

        # Prepare blob for network
        blob = cv2.dnn.blobFromImage(
            frame,
            0.007843,  # Scale factor (1/127.5)
            (300, 300),  # Input size
            127.5  # Mean subtraction
        )

        # Run detection
        self.net.setInput(blob)
        detections = self.net.forward()

        # Parse results
        person_found = False
        vehicle_found = False
        results = []

        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]

            if confidence > self.confidence_threshold:
                # Get class
                idx = int(detections[0, 0, i, 1])
                if idx >= len(self.CLASSES):
                    continue

                class_name = self.CLASSES[idx]

                # Only care about people and vehicles
                if class_name == self.PERSON_CLASS:
                    person_found = True
                elif class_name in self.VEHICLE_CLASSES:
                    vehicle_found = True
                else:
                    continue  # Ignore other objects

                # Get bounding box
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (startX, startY, endX, endY) = box.astype("int")

                results.append({
                    'class': class_name,
                    'confidence': float(confidence),
                    'bbox': (startX, startY, endX, endY)
                })

        # Update state and log events
        self._update_detection_state(person_found, vehicle_found)

        return person_found, vehicle_found, results

    def _update_detection_state(self, person_found: bool, vehicle_found: bool):
        """Update detection state and log events to database"""
        now = datetime.now()
        event_type = None

        # Determine event type (prioritize person over vehicle)
        if person_found:
            event_type = "person"
            self.last_person_time = now
        elif vehicle_found:
            event_type = "vehicle"
            self.last_vehicle_time = now

        # Handle event state changes
        if event_type and not self.current_event_type:
            # New event started
            self._start_ai_event(event_type)

        elif event_type and self.current_event_type != event_type:
            # Event type changed (e.g., vehicle -> person)
            self._end_ai_event()
            self._start_ai_event(event_type)

        elif not event_type and self.current_event_type:
            # Event ended
            self._end_ai_event()

        # Increment frame count if event is active
        if event_type:
            self.event_frame_count += 1

        # Update detection flags
        self.person_detected = person_found
        self.vehicle_detected = vehicle_found

    def _start_ai_event(self, event_type: str):
        """Start a new AI detection event"""
        self.current_event_type = event_type
        self.event_start_time = datetime.now()
        self.event_frame_count = 1

        logger.info(f"AI: {event_type.upper()} detected on {self.camera_name}")

    def _end_ai_event(self):
        """End current AI detection event and save to database"""
        if not self.current_event_type or not self.event_start_time:
            return

        # Calculate duration
        duration = (datetime.now() - self.event_start_time).total_seconds()

        # Log to database through recorder
        if self.recorder and self.recorder.playback_db:
            # Store as motion event with metadata
            # We can add an 'ai_type' column to motion_events table later
            # For now, use intensity field to encode type:
            # intensity = 1.0 for person, 0.5 for vehicle
            intensity = 1.0 if self.current_event_type == "person" else 0.5

            self.recorder.playback_db.add_motion_event(
                camera_name=self.camera_name,
                event_time=self.event_start_time,
                duration_seconds=duration,
                frame_count=self.event_frame_count,
                intensity=intensity,
                event_type=f"ai_{self.current_event_type}"  # "ai_person" or "ai_vehicle"
            )

            logger.info(
                f"AI: {self.current_event_type.upper()} event logged for {self.camera_name}: "
                f"{duration:.1f}s, {self.event_frame_count} frames"
            )

        # Reset
        self.current_event_type = None
        self.event_start_time = None
        self.event_frame_count = 0

    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[dict]
    ) -> np.ndarray:
        """
        Draw bounding boxes around detected people and vehicles

        Args:
            frame: Original BGR frame
            detections: List of detection dicts

        Returns:
            Frame with detections drawn
        """
        result = frame.copy()

        for det in detections:
            class_name = det['class']
            confidence = det['confidence']
            (startX, startY, endX, endY) = det['bbox']

            # Color: Red for person, Blue for vehicle
            color = (0, 0, 255) if class_name == "person" else (255, 0, 0)

            # Draw box
            cv2.rectangle(result, (startX, startY), (endX, endY), color, 2)

            # Draw label
            label = f"{class_name.upper()}: {confidence:.2f}"
            y = startY - 10 if startY - 10 > 10 else startY + 10

            cv2.putText(
                result,
                label,
                (startX, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2
            )

        return result

    def reset(self):
        """Reset detector state"""
        self.person_detected = False
        self.vehicle_detected = False
        self.last_person_time = None
        self.last_vehicle_time = None

        if self.current_event_type:
            self._end_ai_event()


class AIDetectionMonitor:
    """Monitors AI detection across multiple cameras"""

    def __init__(self, confidence_threshold: float = 0.5):
        self.confidence_threshold = confidence_threshold
        self.detectors: dict[str, AIObjectDetector] = {}
        self.is_running = False

    def add_camera(
        self,
        camera_name: str,
        recorder=None,
        confidence_threshold: Optional[float] = None
    ) -> AIObjectDetector:
        """Add a camera to AI monitoring"""
        if camera_name in self.detectors:
            logger.warning(f"AI detector for {camera_name} already exists")
            return self.detectors[camera_name]

        threshold = confidence_threshold or self.confidence_threshold

        detector = AIObjectDetector(
            confidence_threshold=threshold,
            camera_name=camera_name,
            recorder=recorder
        )

        self.detectors[camera_name] = detector
        logger.info(f"Added AI detector for {camera_name}")

        return detector

    def remove_camera(self, camera_name: str) -> bool:
        """Remove a camera from AI monitoring"""
        if camera_name in self.detectors:
            detector = self.detectors[camera_name]
            detector.reset()
            del self.detectors[camera_name]
            logger.info(f"Removed AI detector for {camera_name}")
            return True
        return False

    def get_detector(self, camera_name: str) -> Optional[AIObjectDetector]:
        """Get AI detector for a camera"""
        return self.detectors.get(camera_name)

    async def monitor_recorder(
        self,
        camera_name: str,
        recorder,
        check_interval: int = 30  # Check every 30 frames (about 1 second at 30fps)
    ):
        """
        Monitor AI detection from a recorder's frame queue

        Args:
            camera_name: Camera name
            recorder: RTSPRecorder instance
            check_interval: Frames to skip between AI checks (higher = less CPU)
        """
        import asyncio

        detector = self.get_detector(camera_name)
        if not detector:
            logger.error(f"No AI detector for {camera_name}")
            return

        frame_count = 0

        while self.is_running:
            try:
                # Get latest frame from recorder
                frame = recorder.get_latest_frame()

                if frame is not None:
                    frame_count += 1

                    # Only check every Nth frame to reduce CPU usage
                    # AI detection is more expensive than motion detection
                    if frame_count % check_interval == 0:
                        person_found, vehicle_found, detections = detector.detect_objects(frame)

                        if person_found or vehicle_found:
                            types = []
                            if person_found:
                                types.append("PERSON")
                            if vehicle_found:
                                types.append("VEHICLE")

                            logger.debug(
                                f"AI: {camera_name} - Detected: {', '.join(types)} "
                                f"({len(detections)} object(s))"
                            )

                await asyncio.sleep(0.01)  # Small delay to prevent busy loop

            except Exception as e:
                logger.error(f"Error in AI monitoring for {camera_name}: {e}")
                await asyncio.sleep(1)

    async def start_monitoring(self, recorder_manager):
        """Start AI monitoring for all cameras"""
        import asyncio

        self.is_running = True

        tasks = []
        for camera_name, recorder in recorder_manager.recorders.items():
            if camera_name in self.detectors:
                task = asyncio.create_task(
                    self.monitor_recorder(camera_name, recorder)
                )
                tasks.append(task)

        if tasks:
            logger.info(f"Started AI monitoring for {len(tasks)} camera(s)")
            await asyncio.gather(*tasks)

    def stop_monitoring(self):
        """Stop AI monitoring for all cameras"""
        self.is_running = False
        logger.info("Stopped AI monitoring")
