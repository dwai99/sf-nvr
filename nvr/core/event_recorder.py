"""High-resolution, motion-triggered event recording.

Cameras record the low-bandwidth sub-stream continuously (reliable over WiFi).
When motion is detected, this briefly pulls the full-res MAIN stream and records
a high-quality clip of the event. A concurrency cap keeps only 1-2 main streams
open at a time, so the WiFi airtime that 7 simultaneous main streams would
saturate stays clear (motion is usually on one or two cameras at once).

Clips are stored under <storage>/<camera_id>/events/ and registered in the
recording_segments table with source='event' (kept out of the main timeline).
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)


class HighResEventRecorder:
    def __init__(
        self,
        storage_path,
        playback_db,
        max_concurrent: int = 2,
        cooldown_seconds: float = 5.0,
        max_duration_seconds: float = 60.0,
        output_width: int = 1920,
        max_seconds_per_hour: float = 600.0,
    ):
        self.storage_path = Path(storage_path)
        self.playback_db = playback_db
        self.max_concurrent = max_concurrent
        self.cooldown_seconds = cooldown_seconds
        self.max_duration_seconds = max_duration_seconds
        self.output_width = output_width
        # Hard cap on how many seconds of high-res event footage each camera may
        # record per rolling hour. Without this, a scene with near-constant motion
        # (trees, traffic, a busy patio) records essentially continuously and
        # fills the disk — which is exactly what happened.
        self.max_seconds_per_hour = max_seconds_per_hour
        self._lock = threading.Lock()
        self._active = set()  # camera_ids currently capturing
        self._sem = threading.Semaphore(max_concurrent)
        self._spent = {}  # camera_id -> list of (finish_monotonic, seconds) in the last hour

    def trigger(self, camera_id: str, camera_name: str, main_url: str, detector=None) -> None:
        """Begin a high-res capture on motion start, if a slot is free and this
        camera isn't already capturing. Non-blocking."""
        with self._lock:
            if camera_id in self._active:
                return  # already capturing; the running loop extends with continued motion
            if self._spent_last_hour(camera_id) >= self.max_seconds_per_hour:
                logger.debug(
                    f"High-res event skipped for {camera_name}: hourly limit "
                    f"({self.max_seconds_per_hour:.0f}s) reached"
                )
                return
            if not self._sem.acquire(blocking=False):
                logger.debug(
                    f"High-res event skipped for {camera_name}: {self.max_concurrent} capture(s) already running"
                )
                return
            self._active.add(camera_id)
        threading.Thread(
            target=self._capture,
            args=(camera_id, camera_name, main_url, detector),
            daemon=True,
            name=f"Event-{camera_name}",
        ).start()

    def _spent_last_hour(self, camera_id) -> float:
        """Seconds of event footage recorded for this camera in the last hour.
        Caller must hold self._lock."""
        cutoff = time.monotonic() - 3600
        entries = [(t, s) for (t, s) in self._spent.get(camera_id, []) if t >= cutoff]
        self._spent[camera_id] = entries
        return sum(s for _, s in entries)

    def _capture(self, camera_id, camera_name, main_url, detector):
        cap = None
        writer = None
        filepath = None
        start_dt = datetime.now()
        start = None
        frames = 0
        ow = oh = 0
        try:
            cap = cv2.VideoCapture(main_url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                logger.warning(f"High-res event: could not open main stream for {camera_name}")
                return

            sw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or self.output_width
            sh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or int(self.output_width * 9 / 16)
            fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
            ow, oh = sw, sh
            if sw > self.output_width:
                ow = self.output_width
                oh = int(sh * (self.output_width / sw))

            events_dir = self.storage_path / camera_id / "events"
            events_dir.mkdir(parents=True, exist_ok=True)
            ts = start_dt.strftime("%Y%m%d_%H%M%S")
            filepath = events_dir / f"{ts}_event.mp4"
            n = 1
            while filepath.exists():
                filepath = events_dir / f"{ts}_event_{n}.mp4"
                n += 1

            writer = cv2.VideoWriter(str(filepath), cv2.VideoWriter_fourcc(*"mp4v"), fps, (ow, oh))
            if not writer.isOpened():
                logger.error(f"High-res event: VideoWriter failed to open for {camera_name}")
                return

            logger.info(f"High-res event capture started for {camera_name}: {filepath.name} ({ow}x{oh})")
            start = time.monotonic()
            last_motion = start
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if sw > self.output_width:
                    frame = cv2.resize(frame, (ow, oh), interpolation=cv2.INTER_AREA)
                writer.write(frame)
                frames += 1

                now = time.monotonic()
                if detector is not None and getattr(detector, "motion_detected", False):
                    last_motion = now
                if now - start >= self.max_duration_seconds:
                    break
                if now - last_motion >= self.cooldown_seconds:
                    break
        except Exception as e:
            logger.error(f"High-res event capture error for {camera_name}: {e}")
        finally:
            duration = int(time.monotonic() - start) if start is not None else 0
            if writer is not None:
                writer.release()
            if cap is not None:
                cap.release()
            if filepath is not None and frames > 0 and self.playback_db:
                try:
                    size = filepath.stat().st_size if filepath.exists() else 0
                    self.playback_db.add_segment(
                        camera_id=camera_id,
                        camera_name=camera_name,
                        file_path=str(filepath),
                        start_time=start_dt,
                        end_time=datetime.now(),
                        duration_seconds=duration,
                        file_size_bytes=size,
                        width=ow,
                        height=oh,
                        source="event",
                    )
                    logger.info(
                        f"High-res event clip saved for {camera_name}: {filepath.name} "
                        f"({duration}s, {frames} frames, {size / 1e6:.1f}MB)"
                    )
                except Exception as e:
                    logger.error(f"High-res event: failed to register clip in DB: {e}")
            with self._lock:
                self._active.discard(camera_id)
                if duration > 0:
                    self._spent.setdefault(camera_id, []).append((time.monotonic(), duration))
            self._sem.release()
