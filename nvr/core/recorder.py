"""RTSP stream recording and management"""

import asyncio
import logging
import os
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime, timedelta
import threading
import queue
import time
import gc

# Set OpenCV FFmpeg options for TCP RTSP transport BEFORE any OpenCV usage
# This MUST be set before cv2.VideoCapture is called
os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|timeout;60000000|stimeout;10000000|max_delay;10000000'

logger = logging.getLogger(__name__)


class RTSPRecorder:
    """Records RTSP streams to disk with automatic segmentation"""

    def __init__(
        self,
        camera_name: str,
        rtsp_url: str,
        storage_path: Path,
        segment_duration: int = 300,
        codec: str = 'h264',
        container: str = 'mp4',
        playback_db=None
    ):
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url
        self.storage_path = storage_path
        self.segment_duration = segment_duration
        self.codec = codec
        self.container = container
        self.playback_db = playback_db

        self.is_recording = False
        self.capture: Optional[cv2.VideoCapture] = None
        self.writer: Optional[cv2.VideoWriter] = None
        self.current_segment_start: Optional[datetime] = None
        self.current_segment_path: Optional[Path] = None
        # CRITICAL: Store compressed JPEG bytes instead of raw frames to save memory
        # Queue holds only 2 frames (latest + backup) to minimize memory usage
        # Raw 4K frame = 24MB, JPEG = ~200KB = 120x smaller!
        self.frame_queue: queue.Queue = queue.Queue(maxsize=2)

        # Cache last frame to avoid blank frames when queue is empty
        self.last_frame: Optional[bytes] = None  # Store JPEG bytes, not numpy array
        self.frame_lock = threading.Lock()

        # Motion tracking
        self.motion_event_start: Optional[datetime] = None
        self.motion_frame_count: int = 0

        # Callbacks
        self.on_motion_detected: Optional[Callable] = None

        # Create camera storage directory
        self.camera_storage = storage_path / self._sanitize_name(camera_name)
        self.camera_storage.mkdir(parents=True, exist_ok=True)

    def _sanitize_name(self, name: str) -> str:
        """Sanitize camera name for filesystem"""
        return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name)

    async def start(self) -> bool:
        """Start recording stream"""
        if self.is_recording:
            logger.warning(f"Recorder for {self.camera_name} already running")
            return False

        logger.info(f"Starting recorder for {self.camera_name}")
        logger.info(f"RTSP URL: {self.rtsp_url}")

        self.is_recording = True

        # Start recording in separate thread to avoid blocking
        self.record_thread = threading.Thread(target=self._record_loop, daemon=True)
        self.record_thread.start()

        return True

    def stop(self) -> None:
        """Stop recording stream"""
        logger.info(f"Stopping recorder for {self.camera_name}")
        self.is_recording = False

        # Don't block waiting for thread - cleanup will happen in thread
        # Reduced timeout from 5s to 0.5s for faster shutdown
        if self.record_thread and self.record_thread.is_alive():
            self.record_thread.join(timeout=0.5)

        self._cleanup()

    def _record_loop(self) -> None:
        """Main recording loop (runs in separate thread)"""
        retry_delay = 5
        max_retry_delay = 300  # 5 minutes max between retries
        consecutive_failures = 0

        while self.is_recording:
            try:
                # Connect to RTSP stream with TCP transport for reliability
                logger.info(f"Connecting to {self.camera_name}...")

                # Use FFmpeg backend for RTSP (TCP transport set via environment variable)
                self.capture = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)

                # Set buffer size to 1 to minimize memory usage
                # Single frame buffer reduces memory while TCP transport handles network reliability
                self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not self.capture.isOpened():
                    consecutive_failures += 1

                    # Log less frequently for persistent failures
                    if consecutive_failures <= 3 or consecutive_failures % 10 == 0:
                        logger.error(f"Failed to open RTSP stream for {self.camera_name} (attempt {consecutive_failures})")

                    # Exponential backoff: 5s → 10s → 20s → 40s → 80s → 160s → 300s (5min)
                    self._sleep_if_recording(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    continue

                # Get stream properties
                fps = self.capture.get(cv2.CAP_PROP_FPS)
                width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

                logger.info(f"Stream opened: {width}x{height} @ {fps}fps")

                # Reset counters on successful connection
                retry_delay = 5
                consecutive_failures = 0

                # Record frames
                self._record_frames(fps, width, height)

            except Exception as e:
                consecutive_failures += 1

                # Log less frequently for persistent failures
                if consecutive_failures <= 3 or consecutive_failures % 10 == 0:
                    logger.error(f"Error in recording loop for {self.camera_name}: {e} (attempt {consecutive_failures})")

                self._sleep_if_recording(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

            finally:
                self._cleanup()

    def _record_frames(self, fps: float, width: int, height: int) -> None:
        """Record frames from stream"""
        frames_since_start = 0
        frames_per_segment = int(fps * self.segment_duration)
        consecutive_failures = 0
        max_consecutive_failures = 30  # Allow 30 consecutive failures before reconnecting

        # CRITICAL: Determine recording dimensions BEFORE starting any segments
        # Downscale to 1080p max to save memory (still high quality for recording)
        recording_width = width
        recording_height = height
        if width > 1920:
            scale = 1920 / width
            recording_width = 1920
            recording_height = int(height * scale)

        logger.info(f"Recording dimensions: {recording_width}x{recording_height} (source: {width}x{height})")

        while self.is_recording:
            ret, frame = self.capture.read()

            if not ret:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(f"Failed to read frame from {self.camera_name} ({consecutive_failures} consecutive failures)")
                    break
                # Brief sleep to avoid tight loop on temporary network issues
                time.sleep(0.1)
                continue

            # Reset failure counter on successful read
            consecutive_failures = 0

            # CRITICAL: Scale down frame to recording dimensions if needed
            if width > 1920:
                frame = cv2.resize(frame, (recording_width, recording_height), interpolation=cv2.INTER_AREA)

            # Start new segment if needed
            if frames_since_start % frames_per_segment == 0:
                self._start_new_segment(fps, recording_width, recording_height)
                frames_since_start = 0

            # Write frame to disk
            if self.writer:
                success = self.writer.write(frame)
                if frames_since_start == 1:  # Log only first frame
                    logger.info(f"First frame write result: {success}, frame shape: {frame.shape}")

            # Only compress and queue every 2nd frame for live viewing to reduce memory load
            # This gives us ~7-8 FPS for live view (good balance of smoothness and memory)
            if frames_since_start % 2 == 0:
                # Compress frame to JPEG for live viewing (saves memory)
                # Quality 85 is good balance between size and quality
                _, jpeg_bytes = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                jpeg_data = jpeg_bytes.tobytes()

                # CRITICAL: Explicitly delete jpeg_bytes to free memory immediately
                del jpeg_bytes

                # Put compressed frame in queue for live viewing
                try:
                    self.frame_queue.put_nowait(jpeg_data)
                except queue.Full:
                    # Skip frame if queue is full
                    try:
                        self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait(jpeg_data)
                    except queue.Empty:
                        pass

            # CRITICAL: Explicitly delete frame to free memory immediately
            # Without this, Python's garbage collector may not free memory fast enough
            del frame

            frames_since_start += 1

            # Force garbage collection every 50 frames to prevent memory accumulation
            # This is critical for preventing Python from holding onto deleted numpy arrays
            if frames_since_start % 50 == 0:
                gc.collect()

    def _start_new_segment(self, fps: float, width: int, height: int) -> None:
        """Start a new recording segment"""
        # Finalize previous segment in database
        if self.writer and self.current_segment_path and self.playback_db:
            self.writer.release()

            # Calculate actual segment duration and size
            end_time = datetime.now()
            duration = int((end_time - self.current_segment_start).total_seconds())
            file_size = self.current_segment_path.stat().st_size if self.current_segment_path.exists() else 0

            # Update database with segment info
            self.playback_db.update_segment_end(
                self.camera_name,
                str(self.current_segment_path),
                end_time,
                duration,
                file_size
            )

        # Generate filename with timestamp
        self.current_segment_start = datetime.now()
        timestamp = self.current_segment_start.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}.{self.container}"
        filepath = self.camera_storage / filename
        self.current_segment_path = filepath

        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*self._get_fourcc())

        # IMPORTANT: Use mp4v codec on macOS to avoid FFmpeg write errors
        # H264 codec has issues with VideoWriter on some systems
        import platform
        if platform.system() == 'Darwin':  # macOS
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            logger.info(f"Using mp4v codec for macOS compatibility")

        logger.info(f"Creating VideoWriter: {filepath}, fps={fps}, dimensions={width}x{height}, fourcc={fourcc}")

        self.writer = cv2.VideoWriter(
            str(filepath),
            fourcc,
            fps,
            (width, height)
        )

        logger.info(f"VideoWriter created, isOpened={self.writer.isOpened()}")

        # Verify writer opened successfully
        if not self.writer.isOpened():
            logger.error(f"Failed to open VideoWriter for {filepath}")
            logger.error(f"Attempted codec: {fourcc}, fps: {fps}, dimensions: {width}x{height}")
            # Try fallback to mjpeg
            logger.info("Trying fallback to MJPG codec...")
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            self.writer = cv2.VideoWriter(
                str(filepath),
                fourcc,
                fps,
                (width, height)
            )
            if not self.writer.isOpened():
                logger.error("VideoWriter failed to open with MJPG fallback!")
                self.writer = None
                return

        # Add segment to database
        if self.playback_db:
            self.playback_db.add_segment(
                camera_name=self.camera_name,
                file_path=str(filepath),
                start_time=self.current_segment_start,
                fps=fps,
                width=width,
                height=height
            )

        logger.info(f"Started new segment: {filepath}")

    def _get_fourcc(self) -> str:
        """Get FourCC code for codec"""
        codec_map = {
            'h264': 'H264',
            'h265': 'HEVC',
            'mjpeg': 'MJPG',
            'mpeg4': 'MP4V'
        }
        return codec_map.get(self.codec.lower(), 'H264')

    def _cleanup(self) -> None:
        """Clean up resources"""
        if self.writer:
            self.writer.release()
            self.writer = None

        if self.capture:
            self.capture.release()
            self.capture = None

    def _sleep_if_recording(self, seconds: int) -> None:
        """Sleep for specified seconds if still recording"""
        # Use smaller sleep intervals for faster response to stop signal
        for _ in range(seconds * 10):
            if not self.is_recording:
                break
            threading.Event().wait(0.1)  # 100ms intervals instead of 1s

    def get_latest_frame(self) -> Optional[bytes]:
        """Get the latest frame from the stream (for live view)
        Returns JPEG-compressed frame as bytes (not numpy array) to save memory
        """
        try:
            # Try to get fresh frame from queue (already JPEG compressed)
            jpeg_data = self.frame_queue.get_nowait()
            # Update cached frame
            with self.frame_lock:
                self.last_frame = jpeg_data
            return jpeg_data
        except queue.Empty:
            # Return cached frame instead of None to avoid blank frames
            with self.frame_lock:
                return self.last_frame

    def log_motion_event(self, intensity: float = 0.0) -> None:
        """Log a motion detection event to the database"""
        if not self.playback_db:
            return

        now = datetime.now()

        # Start new motion event
        if self.motion_event_start is None:
            self.motion_event_start = now
            self.motion_frame_count = 1
        else:
            # Accumulate frames
            self.motion_frame_count += 1

    def end_motion_event(self) -> None:
        """End current motion event and save to database"""
        if not self.playback_db or self.motion_event_start is None:
            return

        # Calculate duration
        duration = (datetime.now() - self.motion_event_start).total_seconds()

        # Save to database
        self.playback_db.add_motion_event(
            camera_name=self.camera_name,
            event_time=self.motion_event_start,
            duration_seconds=duration,
            frame_count=self.motion_frame_count
        )

        logger.debug(
            f"Motion event logged for {self.camera_name}: "
            f"{duration:.1f}s, {self.motion_frame_count} frames"
        )

        # Reset
        self.motion_event_start = None
        self.motion_frame_count = 0


class RecorderManager:
    """Manages multiple camera recorders"""

    def __init__(self, storage_path: Path, segment_duration: int = 300, playback_db=None):
        self.storage_path = storage_path
        self.segment_duration = segment_duration
        self.playback_db = playback_db
        self.recorders: dict[str, RTSPRecorder] = {}

    async def add_camera(
        self,
        camera_name: str,
        rtsp_url: str,
        auto_start: bool = True
    ) -> RTSPRecorder:
        """Add a camera recorder"""
        if camera_name in self.recorders:
            logger.warning(f"Recorder for {camera_name} already exists")
            return self.recorders[camera_name]

        recorder = RTSPRecorder(
            camera_name=camera_name,
            rtsp_url=rtsp_url,
            storage_path=self.storage_path,
            segment_duration=self.segment_duration,
            playback_db=self.playback_db
        )

        self.recorders[camera_name] = recorder

        if auto_start:
            await recorder.start()

        return recorder

    async def remove_camera(self, camera_name: str) -> bool:
        """Remove a camera recorder"""
        if camera_name not in self.recorders:
            return False

        recorder = self.recorders[camera_name]
        recorder.stop()
        del self.recorders[camera_name]

        return True

    def get_recorder(self, camera_name: str) -> Optional[RTSPRecorder]:
        """Get recorder by camera name"""
        return self.recorders.get(camera_name)

    async def start_all(self) -> None:
        """Start all recorders"""
        for recorder in self.recorders.values():
            await recorder.start()

    def stop_all(self) -> None:
        """Stop all recorders"""
        for recorder in self.recorders.values():
            recorder.stop()

    def cleanup_old_recordings(self, retention_days: int) -> None:
        """Delete recordings older than retention period"""
        cutoff = datetime.now() - timedelta(days=retention_days)
        deleted_count = 0

        for camera_dir in self.storage_path.iterdir():
            if not camera_dir.is_dir():
                continue

            for video_file in camera_dir.glob(f"*.{self.container}"):
                try:
                    # Parse timestamp from filename
                    timestamp_str = video_file.stem
                    file_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                    if file_time < cutoff:
                        video_file.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted old recording: {video_file}")

                except Exception as e:
                    logger.warning(f"Error processing {video_file}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old recordings")