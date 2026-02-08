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
        playback_db=None,
        camera_id: Optional[str] = None,
        recording_mode_manager=None
    ):
        self.camera_name = camera_name
        self.camera_id = camera_id or self._sanitize_name(camera_name)  # Fallback to name if no ID
        self.rtsp_url = rtsp_url
        self.storage_path = storage_path
        self.segment_duration = segment_duration
        self.codec = codec
        self.container = container
        self.playback_db = playback_db
        self.recording_mode_manager = recording_mode_manager

        self.is_recording = False
        self.streaming_only = False  # If True, connect for live view but don't record to disk
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
        self.has_motion = False  # Current motion state
        self.last_motion_time: Optional[datetime] = None
        self.motion_timeout_seconds: int = 5  # Stop recording after N seconds of no motion

        # Recording mode tracking
        self.actively_writing = False  # True when actually writing frames to disk
        self.buffered_frames = []  # Pre-motion buffer for motion-only mode

        # Callbacks
        self.on_motion_detected: Optional[Callable] = None

        # Health tracking
        self.last_frame_time: Optional[datetime] = None
        self.last_connection_attempt: Optional[datetime] = None
        self.last_successful_connection: Optional[datetime] = None
        self.total_reconnects: int = 0
        self.consecutive_failures: int = 0
        self.stream_fps: float = 0.0
        self.stream_width: int = 0
        self.stream_height: int = 0

        # Create camera storage directory using camera_id (stable across renames)
        self.camera_storage = storage_path / self.camera_id
        self.camera_storage.mkdir(parents=True, exist_ok=True)

    def _sanitize_name(self, name: str) -> str:
        """Sanitize camera name for filesystem"""
        return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name)

    async def start(self, streaming_only: bool = False) -> bool:
        """Start recording stream

        Args:
            streaming_only: If True, connect for live view but don't record to disk
        """
        if self.is_recording:
            logger.warning(f"Recorder for {self.camera_name} already running")
            return False

        self.streaming_only = streaming_only
        mode = "streaming only" if streaming_only else "recording"
        logger.info(f"Starting recorder for {self.camera_name} ({mode})")
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
                self.last_connection_attempt = datetime.now()

                # Use FFmpeg backend for RTSP (TCP transport set via environment variable)
                self.capture = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)

                # Set buffer size to 1 to minimize memory usage
                # Single frame buffer reduces memory while TCP transport handles network reliability
                self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not self.capture.isOpened():
                    consecutive_failures += 1
                    self.consecutive_failures = consecutive_failures

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

                logger.info(f"Stream opened for {self.camera_name}: {width}x{height} @ {fps}fps")

                # Track successful connection and stream properties
                self.last_successful_connection = datetime.now()
                self.stream_fps = fps
                self.stream_width = width
                self.stream_height = height
                if consecutive_failures > 0:
                    self.total_reconnects += 1

                # Reset counters on successful connection
                retry_delay = 5
                consecutive_failures = 0
                self.consecutive_failures = 0

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
        consecutive_failures = 0
        max_consecutive_failures = 30  # Allow 30 consecutive failures before reconnecting

        # CRITICAL: Determine recording dimensions BEFORE starting any segments
        # Get per-camera resolution if configured, otherwise fall back to global setting
        from nvr.core.config import config

        # Look up this camera's resolution setting
        cameras = config.get('cameras', [])
        camera_resolution = None
        for cam in cameras:
            if cam.get('id') == self.camera_id or cam.get('name') == self.camera_name:
                camera_resolution = cam.get('resolution')
                break

        # Fall back to global max_resolution if no per-camera setting
        max_resolution = camera_resolution or config.get('recording.max_resolution', 720)

        # Map resolution setting to width
        resolution_map = {
            1080: 1920,
            720: 1280,
            480: 854,
            360: 640
        }
        max_width = resolution_map.get(max_resolution, 1280)

        # Downscale if source exceeds configured max resolution
        recording_width = width
        recording_height = height
        if width > max_width:
            scale = max_width / width
            recording_width = max_width
            recording_height = int(height * scale)

        logger.info(f"Recording dimensions: {recording_width}x{recording_height} (source: {width}x{height}, max: {max_resolution}p)")

        # Track when the next segment should start (aligned to clock intervals)
        next_segment_time = self._get_next_segment_boundary()
        current_segment_started = False

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
            self.last_frame_time = datetime.now()

            # CRITICAL: Scale down frame to recording dimensions if needed
            if width > max_width:
                frame = cv2.resize(frame, (recording_width, recording_height), interpolation=cv2.INTER_AREA)

            # Only handle recording if not in streaming-only mode
            if not self.streaming_only:
                # Check if we should be recording based on mode and motion state
                now = datetime.now()
                should_record = self._should_record_frame(now)

                # Start new segment if needed and we should be recording
                if should_record:
                    if not current_segment_started or now >= next_segment_time:
                        self._start_new_segment(fps, recording_width, recording_height)
                        next_segment_time = self._get_next_segment_boundary()
                        current_segment_started = True
                        self.actively_writing = True

                    # Write frame to disk
                    if self.writer:
                        self.writer.write(frame)
                else:
                    # Not recording - close current segment if open
                    if self.actively_writing and self.writer:
                        self._close_current_segment()
                        self.actively_writing = False
                        current_segment_started = False

            # Compress frame to JPEG for live viewing (saves memory)
            # Quality 85 is good balance between size and quality
            success, jpeg_bytes = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

            if success and jpeg_bytes is not None:
                # Make an immutable copy of the bytes immediately
                jpeg_data = bytes(jpeg_bytes.tobytes())

                # Validate JPEG structure before queuing
                # Must start with FFD8 (SOI) and end with FFD9 (EOI)
                if (len(jpeg_data) > 1000 and
                    jpeg_data[0:2] == b'\xff\xd8' and
                    jpeg_data[-2:] == b'\xff\xd9'):

                    # Put compressed frame in queue for live viewing
                    with self.frame_lock:
                        try:
                            self.frame_queue.put_nowait(jpeg_data)
                        except queue.Full:
                            # Replace oldest frame with new one
                            try:
                                self.frame_queue.get_nowait()
                                self.frame_queue.put_nowait(jpeg_data)
                            except queue.Empty:
                                pass
                        # Always update last_frame for fallback
                        self.last_frame = jpeg_data

            # CRITICAL: Explicitly delete to free memory immediately
            del jpeg_bytes

            # CRITICAL: Explicitly delete frame to free memory immediately
            # Without this, Python's garbage collector may not free memory fast enough
            del frame

    def _get_next_segment_boundary(self) -> datetime:
        """Calculate the next segment boundary aligned to clock intervals

        For 5-minute (300 second) segments: aligns to 00:00, 00:05, 00:10, 00:15, etc.
        This ensures consistent filenames across restarts.
        """
        now = datetime.now()

        # Convert segment duration from seconds to minutes
        segment_minutes = self.segment_duration // 60

        # Calculate minutes since midnight
        minutes_since_midnight = now.hour * 60 + now.minute

        # Round up to next segment boundary
        next_boundary_minutes = ((minutes_since_midnight // segment_minutes) + 1) * segment_minutes

        # Convert back to hours and minutes
        next_hour = next_boundary_minutes // 60
        next_minute = next_boundary_minutes % 60

        # Handle day rollover
        if next_hour >= 24:
            next_day = now + timedelta(days=1)
            return datetime(next_day.year, next_day.month, next_day.day, 0, 0, 0)

        return datetime(now.year, now.month, now.day, next_hour, next_minute, 0)

    def _should_record_frame(self, now: datetime) -> bool:
        """
        Determine if we should record the current frame based on recording mode

        Args:
            now: Current datetime

        Returns:
            True if frame should be recorded
        """
        # If no recording mode manager, default to continuous recording
        if not self.recording_mode_manager:
            return True

        # Check if mode allows recording
        should_record = self.recording_mode_manager.should_record(
            self.camera_name,
            has_motion=self.has_motion,
            dt=now
        )

        # Handle post-motion timeout for motion-only mode
        if should_record and self.has_motion:
            self.last_motion_time = now
        elif not self.has_motion and self.last_motion_time:
            # Check if we're still in post-motion timeout period
            time_since_motion = (now - self.last_motion_time).total_seconds()
            config = self.recording_mode_manager.get_camera_config(self.camera_name)
            if time_since_motion < config.post_motion_seconds:
                should_record = True  # Keep recording for post-motion duration

        return should_record

    def update_motion_state(self, has_motion: bool):
        """
        Update the current motion state for this recorder

        Args:
            has_motion: Whether motion is currently detected
        """
        self.has_motion = has_motion

    def _close_current_segment(self):
        """Close the current recording segment"""
        if self.writer and self.current_segment_path and self.playback_db:
            self.writer.release()
            self.writer = None

            # Calculate actual segment duration and size
            end_time = datetime.now()
            duration = int((end_time - self.current_segment_start).total_seconds())
            file_size = self.current_segment_path.stat().st_size if self.current_segment_path.exists() else 0

            # Update database with segment info
            self.playback_db.update_segment_end(
                self.camera_id,
                str(self.current_segment_path),
                end_time,
                duration,
                file_size
            )

            # Queue segment for background transcoding for instant playback
            try:
                from nvr.core.transcoder import get_transcoder
                transcoder = get_transcoder()
                transcoder.queue_transcode(self.current_segment_path)
            except Exception as e:
                logger.warning(f"Failed to queue transcode for {self.current_segment_path}: {e}")

            logger.info(f"Closed segment for {self.camera_name}: {self.current_segment_path.name} ({duration}s, {file_size / (1024*1024):.1f}MB)")

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
                self.camera_id,
                str(self.current_segment_path),
                end_time,
                duration,
                file_size
            )

            # Queue segment for background transcoding for instant playback
            try:
                from nvr.core.transcoder import get_transcoder
                transcoder = get_transcoder()
                transcoder.queue_transcode(self.current_segment_path)
            except Exception as e:
                logger.warning(f"Failed to queue transcode for {self.current_segment_path}: {e}")

        # Use current clock time rounded to segment boundary for consistent filenames
        # This ensures files have predictable names like 20260119_143000.mp4 (2:30 PM)
        now = datetime.now()
        segment_minutes = self.segment_duration // 60
        minutes_since_midnight = now.hour * 60 + now.minute
        boundary_minutes = (minutes_since_midnight // segment_minutes) * segment_minutes
        boundary_hour = boundary_minutes // 60
        boundary_minute = boundary_minutes % 60

        self.current_segment_start = datetime(now.year, now.month, now.day, boundary_hour, boundary_minute, 0)
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
                camera_id=self.camera_id,
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

    def _is_frame_corrupted(self, frame: np.ndarray) -> bool:
        """Check if frame appears corrupted (decode artifacts)

        Corrupted frames from H.264/H.265 decode errors often have:
        - Excessive green (common decode error color)
        - Large uniform blocks (macroblocking)
        - Very low entropy

        Returns True if frame appears corrupted.
        """
        try:
            # Sample a small region (center 100x100) for speed
            h, w = frame.shape[:2]
            cy, cx = h // 2, w // 2
            sample = frame[cy-50:cy+50, cx-50:cx+50]

            if sample.size == 0:
                return False

            # Check for excessive green (BGR format)
            # Green decode errors have high G, low R/B
            b, g, r = cv2.split(sample)
            mean_g = np.mean(g)
            mean_r = np.mean(r)
            mean_b = np.mean(b)

            # If green dominates significantly, likely corrupted
            if mean_g > 150 and mean_g > (mean_r + 30) and mean_g > (mean_b + 30):
                return True

            # Check for uniform color (low variance = likely solid block)
            variance = np.var(sample)
            if variance < 50:  # Very uniform = likely corrupted
                return True

            return False
        except Exception:
            return False  # On error, assume frame is okay

    def get_latest_frame(self) -> Optional[bytes]:
        """Get the latest frame from the stream (for live view)
        Returns JPEG-compressed frame as bytes (not numpy array) to save memory
        """
        with self.frame_lock:
            try:
                # Try to get fresh frame from queue (already JPEG compressed and validated)
                jpeg_data = self.frame_queue.get_nowait()
                self.last_frame = jpeg_data
                return jpeg_data
            except queue.Empty:
                # Return cached frame instead of None to avoid blank frames
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

        # Only save events that lasted at least 1 second (filter out noise/artifacts)
        # The 3-second cooldown in motion.py ensures events are aggregated properly
        MIN_MOTION_DURATION = 1.0  # seconds
        MIN_MOTION_FRAMES = 10  # at least 10 frames of motion

        if duration >= MIN_MOTION_DURATION and self.motion_frame_count >= MIN_MOTION_FRAMES:
            # Save to database
            self.playback_db.add_motion_event(
                camera_id=self.camera_id,
                event_time=self.motion_event_start,
                duration_seconds=duration,
                frame_count=self.motion_frame_count,
                camera_name=self.camera_name
            )

            logger.debug(
                f"Motion event logged for {self.camera_name}: "
                f"{duration:.1f}s, {self.motion_frame_count} frames"
            )
        else:
            logger.debug(
                f"Motion event discarded for {self.camera_name} (too short): "
                f"{duration:.2f}s, {self.motion_frame_count} frames"
            )

        # Reset
        self.motion_event_start = None
        self.motion_frame_count = 0


class RecorderManager:
    """Manages multiple camera recorders"""

    def __init__(self, storage_path: Path, segment_duration: int = 300, playback_db=None, recording_mode_manager=None):
        self.storage_path = storage_path
        self.segment_duration = segment_duration
        self.playback_db = playback_db
        self.recording_mode_manager = recording_mode_manager
        self.recorders: dict[str, RTSPRecorder] = {}

    async def add_camera(
        self,
        camera_name: str,
        rtsp_url: str,
        camera_id: Optional[str] = None,
        auto_start: bool = True,
        streaming_only: bool = False
    ) -> RTSPRecorder:
        """Add a camera recorder

        Args:
            camera_name: Name of the camera
            rtsp_url: RTSP URL for the camera stream
            camera_id: Unique ID for the camera (used for storage path)
            auto_start: If True, start the recorder immediately
            streaming_only: If True, connect for live view but don't record to disk
        """
        if camera_name in self.recorders:
            logger.warning(f"Recorder for {camera_name} already exists")
            return self.recorders[camera_name]

        recorder = RTSPRecorder(
            camera_name=camera_name,
            rtsp_url=rtsp_url,
            storage_path=self.storage_path,
            segment_duration=self.segment_duration,
            playback_db=self.playback_db,
            camera_id=camera_id,
            recording_mode_manager=self.recording_mode_manager
        )

        self.recorders[camera_name] = recorder

        if auto_start:
            await recorder.start(streaming_only=streaming_only)

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

    def get_recorder_by_id(self, camera_id: str) -> Optional[RTSPRecorder]:
        """Get recorder by camera ID (checks both id and name for compatibility)"""
        # First try direct lookup by name (in case camera_id is actually a name)
        if camera_id in self.recorders:
            return self.recorders[camera_id]

        # Search by camera_id attribute
        for recorder in self.recorders.values():
            if recorder.camera_id == camera_id:
                return recorder

        return None

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