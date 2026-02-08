"""SD Card Recordings Manager for fallback access to camera storage.

Uses ONVIF Profile G services to query and stream recordings stored
on camera SD cards when local NVR storage is unavailable.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import time

logger = logging.getLogger(__name__)


@dataclass
class CachedRecordings:
    """Cache entry for SD card recordings query results."""
    recordings: List[Dict[str, Any]]
    cached_at: float
    start_time: datetime
    end_time: datetime


class SDCardRecordingsManager:
    """
    Manages access to recordings stored on camera SD cards.

    Provides caching to minimize ONVIF queries and methods to merge
    SD card recordings with local NVR recordings.
    """

    def __init__(
        self,
        playback_db,
        cache_duration: int = 300,  # 5 minutes
        query_timeout: float = 30.0
    ):
        """
        Initialize the SD Card Recordings Manager.

        Args:
            playback_db: PlaybackDatabase instance for local recordings
            cache_duration: How long to cache SD card query results (seconds)
            query_timeout: Timeout for ONVIF queries (seconds)
        """
        self.playback_db = playback_db
        self.cache_duration = cache_duration
        self.query_timeout = query_timeout

        # Cache: camera_id -> CachedRecordings
        self._cache: Dict[str, CachedRecordings] = {}

        # ONVIF device connections: camera_id -> ONVIFDevice
        self._onvif_devices: Dict[str, Any] = {}

        # Lock for thread-safe cache operations
        self._cache_lock = asyncio.Lock()

    def register_onvif_device(self, camera_id: str, device) -> None:
        """
        Register an ONVIF device for SD card access.

        Args:
            camera_id: Camera identifier
            device: ONVIFDevice instance with Profile G support
        """
        self._onvif_devices[camera_id] = device
        logger.info(f"Registered ONVIF device for SD card access: {camera_id}")

    def unregister_onvif_device(self, camera_id: str) -> None:
        """Remove an ONVIF device registration."""
        if camera_id in self._onvif_devices:
            del self._onvif_devices[camera_id]
            logger.info(f"Unregistered ONVIF device: {camera_id}")

    def _is_cache_valid(self, camera_id: str, start_time: datetime, end_time: datetime) -> bool:
        """Check if cached results are still valid for the requested time range."""
        if camera_id not in self._cache:
            return False

        cached = self._cache[camera_id]

        # Check if cache has expired
        if time.time() - cached.cached_at > self.cache_duration:
            return False

        # Check if requested range is covered by cached range
        if cached.start_time <= start_time and cached.end_time >= end_time:
            return True

        return False

    async def get_camera_sd_recordings(
        self,
        camera_id: str,
        start_time: datetime,
        end_time: datetime,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get recordings from camera's SD card for a time range.

        Results are cached to avoid repeated ONVIF queries.

        Args:
            camera_id: Camera identifier
            start_time: Start of time range
            end_time: End of time range
            force_refresh: Bypass cache and query camera directly

        Returns:
            List of recording segments from SD card
        """
        async with self._cache_lock:
            # Check cache first (unless force refresh)
            if not force_refresh and self._is_cache_valid(camera_id, start_time, end_time):
                cached = self._cache[camera_id]
                # Filter cached results to requested range
                return [
                    r for r in cached.recordings
                    if (datetime.fromisoformat(r['end_time']) >= start_time and
                        datetime.fromisoformat(r['start_time']) <= end_time)
                ]

        # Query camera for SD card recordings
        device = self._onvif_devices.get(camera_id)
        if not device:
            logger.warning(f"No ONVIF device registered for camera: {camera_id}")
            return []

        # Check Profile G support
        if not device.device_info.get('supports_profile_g', False):
            logger.debug(f"Camera {camera_id} does not support Profile G")
            return []

        try:
            recordings = await asyncio.wait_for(
                device.get_sd_recordings(start_time, end_time),
                timeout=self.query_timeout
            )

            # Cache the results
            async with self._cache_lock:
                self._cache[camera_id] = CachedRecordings(
                    recordings=recordings,
                    cached_at=time.time(),
                    start_time=start_time,
                    end_time=end_time
                )

            # Add camera_id to each recording
            for rec in recordings:
                rec['camera_id'] = camera_id

            logger.info(f"Retrieved {len(recordings)} SD card recordings for {camera_id}")
            return recordings

        except asyncio.TimeoutError:
            logger.error(f"Timeout querying SD card recordings for {camera_id}")
            return []
        except Exception as e:
            logger.error(f"Error querying SD card recordings for {camera_id}: {e}")
            return []

    def identify_local_gaps(
        self,
        local_segments: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime
    ) -> List[Tuple[datetime, datetime]]:
        """
        Find gaps in local recordings where SD card recordings could fill in.

        Args:
            local_segments: List of local recording segments
            start_time: Start of time range to analyze
            end_time: End of time range to analyze

        Returns:
            List of (gap_start, gap_end) tuples representing missing coverage
        """
        if not local_segments:
            # No local recordings - entire range is a gap
            return [(start_time, end_time)]

        gaps = []

        # Sort segments by start time
        sorted_segments = sorted(
            local_segments,
            key=lambda s: datetime.fromisoformat(s['start_time'])
        )

        # Check gap at the beginning
        first_start = datetime.fromisoformat(sorted_segments[0]['start_time'])
        if first_start > start_time:
            gaps.append((start_time, first_start))

        # Check gaps between segments
        for i in range(len(sorted_segments) - 1):
            current_end = datetime.fromisoformat(sorted_segments[i]['end_time'])
            next_start = datetime.fromisoformat(sorted_segments[i + 1]['start_time'])

            if next_start > current_end:
                # Gap found
                gaps.append((current_end, next_start))

        # Check gap at the end
        last_end = datetime.fromisoformat(sorted_segments[-1]['end_time'])
        if last_end < end_time:
            gaps.append((last_end, end_time))

        return gaps

    def merge_recordings(
        self,
        local_segments: List[Dict[str, Any]],
        sd_segments: List[Dict[str, Any]],
        prefer_local: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Merge local and SD card recordings, handling overlaps.

        Args:
            local_segments: Segments from local NVR storage
            sd_segments: Segments from camera SD card
            prefer_local: If True, prefer local recordings over SD card for overlaps

        Returns:
            Merged list of segments, sorted by start time
        """
        if not sd_segments:
            return local_segments

        if not local_segments:
            return sd_segments

        # Mark source on all segments
        for seg in local_segments:
            if 'source' not in seg:
                seg['source'] = 'local'

        for seg in sd_segments:
            if 'source' not in seg:
                seg['source'] = 'sd_card'

        merged = []

        if prefer_local:
            # Add all local segments
            merged.extend(local_segments)

            # Find gaps in local coverage
            gaps = self.identify_local_gaps(
                local_segments,
                datetime.fromisoformat(min(
                    seg['start_time'] for seg in local_segments + sd_segments
                )),
                datetime.fromisoformat(max(
                    seg['end_time'] for seg in local_segments + sd_segments
                ))
            )

            # Add SD segments that fill gaps
            for sd_seg in sd_segments:
                sd_start = datetime.fromisoformat(sd_seg['start_time'])
                sd_end = datetime.fromisoformat(sd_seg['end_time'])

                for gap_start, gap_end in gaps:
                    # Check if SD segment overlaps with this gap
                    if sd_end > gap_start and sd_start < gap_end:
                        merged.append(sd_seg)
                        break
        else:
            # Simple merge - include all segments
            merged = local_segments + sd_segments

        # Sort by start time
        merged.sort(key=lambda s: s['start_time'])

        return merged

    async def get_replay_uri(self, camera_id: str, recording_token: str) -> Optional[str]:
        """
        Get RTSP replay URI for an SD card recording.

        Args:
            camera_id: Camera identifier
            recording_token: Token from SD card recording

        Returns:
            RTSP URL for replay, or None if not available
        """
        device = self._onvif_devices.get(camera_id)
        if not device:
            logger.warning(f"No ONVIF device registered for camera: {camera_id}")
            return None

        try:
            return await device.get_replay_uri(recording_token)
        except Exception as e:
            logger.error(f"Error getting replay URI for {camera_id}: {e}")
            return None

    def clear_cache(self, camera_id: Optional[str] = None) -> None:
        """
        Clear the recordings cache.

        Args:
            camera_id: Specific camera to clear, or None to clear all
        """
        if camera_id:
            if camera_id in self._cache:
                del self._cache[camera_id]
                logger.info(f"Cleared SD card cache for {camera_id}")
        else:
            self._cache.clear()
            logger.info("Cleared all SD card caches")

    def get_supported_cameras(self) -> List[str]:
        """Get list of cameras with Profile G support."""
        return [
            camera_id for camera_id, device in self._onvif_devices.items()
            if device.device_info.get('supports_profile_g', False)
        ]

    async def check_all_profile_g_support(self) -> Dict[str, bool]:
        """
        Check Profile G support for all registered cameras.

        Returns:
            Dict mapping camera_id to Profile G support status
        """
        results = {}
        for camera_id, device in self._onvif_devices.items():
            try:
                supported = await device.check_profile_g_support()
                results[camera_id] = supported
            except Exception as e:
                logger.error(f"Error checking Profile G for {camera_id}: {e}")
                results[camera_id] = False
        return results
