"""Playback API endpoints for video archive access"""

from fastapi import APIRouter, HTTPException, Query, Response, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from pathlib import Path
import logging
import subprocess
import tempfile
import os

logger = logging.getLogger(__name__)

# Cache directory for speed-processed videos
SPEED_CACHE_DIR = Path("recordings/.speed_cache")


def get_speed_processed_video(source_file: Path, speed: float) -> Optional[Path]:
    """
    Get or create a speed-processed version of a video.

    For speeds > 2x, we use FFmpeg to create a truly sped-up video using:
    - setpts filter to change presentation timestamps
    - Frame dropping to reduce file size and improve playback

    Args:
        source_file: Path to the original video file
        speed: Playback speed multiplier (e.g., 4.0 for 4x speed)

    Returns:
        Path to the speed-processed video, or None if processing fails
    """
    if speed <= 2.0:
        return None  # Browser can handle speeds up to 2x natively

    # Create cache directory if needed
    SPEED_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Generate cache filename based on source file and speed
    speed_str = f"{speed:.1f}x".replace(".", "_")
    cache_filename = f"{source_file.stem}_{speed_str}.mp4"
    cached_file = SPEED_CACHE_DIR / cache_filename

    # Check if already cached
    if cached_file.exists():
        # Verify cache is newer than source
        if cached_file.stat().st_mtime >= source_file.stat().st_mtime:
            logger.debug(f"Using cached speed-processed video: {cache_filename}")
            return cached_file

    logger.info(f"Creating {speed}x speed version of {source_file.name}")

    try:
        # FFmpeg command to speed up video:
        # - setpts=PTS/speed: Adjusts timestamps to speed up playback
        # - For audio (if present): atempo filter (limited to 0.5-2.0 range, so we chain them)
        # - Output at reasonable quality with fast encoding

        # Build filter for video speed
        video_filter = f"setpts=PTS/{speed}"

        # For high speeds, also reduce resolution to improve performance
        if speed >= 4.0:
            video_filter += ",scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease"

        ffmpeg_cmd = [
            'ffmpeg',
            '-i', str(source_file),
            '-vf', video_filter,
            '-an',  # Remove audio (doesn't make sense at high speeds)
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '28',  # Slightly lower quality for speed cache (smaller files)
            '-movflags', '+faststart',
            '-y',  # Overwrite existing
            str(cached_file)
        ]

        logger.debug(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            timeout=120  # 2 minute timeout
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg speed processing failed: {result.stderr.decode()}")
            return None

        logger.info(f"Created {speed}x version: {cache_filename} ({cached_file.stat().st_size / 1024 / 1024:.1f}MB)")
        return cached_file

    except subprocess.TimeoutExpired:
        logger.error(f"FFmpeg speed processing timed out for {source_file.name}")
        return None
    except Exception as e:
        logger.error(f"Error creating speed-processed video: {e}")
        return None


def range_requests_response(
    file_path: Path,
    request: Request,
    content_type: str = "video/mp4"
):
    """
    Returns a StreamingResponse that supports HTTP Range requests for video seeking.
    This allows browsers to seek within videos and stream them properly.
    """
    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    headers = {
        "accept-ranges": "bytes",
        "content-type": content_type,
    }

    start = 0
    end = file_size - 1

    if range_header:
        # Parse range header (e.g., "bytes=0-1023")
        range_match = range_header.replace("bytes=", "").split("-")
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if range_match[1] else file_size - 1

        # Ensure valid range
        start = max(0, start)
        end = min(end, file_size - 1)

        # Add content-range header for 206 response
        headers["content-range"] = f"bytes {start}-{end}/{file_size}"

        logger.debug(f"Range request: bytes {start}-{end}/{file_size}")

        def file_iterator():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                chunk_size = 65536  # 64KB chunks

                while remaining > 0:
                    chunk = f.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            file_iterator(),
            status_code=206,  # Partial Content
            headers=headers,
            media_type=content_type
        )

    else:
        # No range requested, send entire file
        headers["content-length"] = str(file_size)

        def file_iterator():
            with open(file_path, "rb") as f:
                chunk_size = 65536  # 64KB chunks
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            file_iterator(),
            status_code=200,
            headers=headers,
            media_type=content_type
        )

router = APIRouter()


class PlaybackRequest(BaseModel):
    """Request model for playback"""
    camera_id: str  # Camera ID
    start_time: str  # ISO format datetime
    end_time: Optional[str] = None  # ISO format datetime
    speed: float = 1.0


class TimeRangeRequest(BaseModel):
    """Request for time range query"""
    start_time: str
    end_time: str
    cameras: Optional[List[str]] = None


@router.get("/api/playback/recordings/{camera_id}")
async def get_camera_recordings(
    camera_id: str,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    start_time: Optional[str] = Query(None, description="ISO format datetime"),
    end_time: Optional[str] = Query(None, description="ISO format datetime"),
    include_sd_card: bool = Query(False, description="Include recordings from camera SD card")
):
    """Get list of recording segments for a camera"""
    from nvr.web.api import playback_db, sd_card_manager
    from nvr.core.config import config

    try:
        # Parse time range
        if date:
            # Get all recordings for a specific date
            start_dt = datetime.fromisoformat(f"{date}T00:00:00")
            end_dt = start_dt + timedelta(days=1)
        elif start_time and end_time:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
        else:
            # Default to last 24 hours
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=1)

        segments = playback_db.get_segments_in_range(camera_id, start_dt, end_dt)

        # Check if we should query SD card
        sd_card_config = config.get('sd_card_fallback', {})
        sd_card_enabled = sd_card_config.get('enabled', True)
        auto_fallback = sd_card_config.get('auto_fallback', True)

        sd_segments = []
        sd_card_available = False

        if sd_card_enabled and sd_card_manager:
            # Query SD card if explicitly requested OR if auto_fallback and no local recordings
            should_query_sd = include_sd_card or (auto_fallback and len(segments) == 0)

            if should_query_sd:
                try:
                    sd_segments = await sd_card_manager.get_camera_sd_recordings(
                        camera_id, start_dt, end_dt
                    )
                    sd_card_available = len(sd_segments) > 0

                    if sd_segments:
                        # Merge with local segments
                        segments = sd_card_manager.merge_recordings(segments, sd_segments)
                        logger.info(f"Merged {len(sd_segments)} SD card recordings for {camera_id}")

                except Exception as e:
                    logger.warning(f"Failed to query SD card for {camera_id}: {e}")

        return {
            'camera_id': camera_id,
            'start_time': start_dt.isoformat(),
            'end_time': end_dt.isoformat(),
            'segment_count': len(segments),
            'segments': segments,
            'sd_card_available': sd_card_available,
            'sd_card_segments': len(sd_segments) if sd_segments else 0
        }

    except Exception as e:
        logger.error(f"Error getting recordings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/recordings")
async def get_all_recordings(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    start_time: Optional[str] = Query(None, description="ISO format datetime"),
    end_time: Optional[str] = Query(None, description="ISO format datetime"),
    include_sd_card: bool = Query(False, description="Include recordings from camera SD cards")
):
    """Get recording segments for all cameras"""
    from nvr.web.api import playback_db, sd_card_manager
    from nvr.core.config import config

    try:
        # Parse time range
        if date:
            start_dt = datetime.fromisoformat(f"{date}T00:00:00")
            end_dt = start_dt + timedelta(days=1)
        elif start_time and end_time:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
            logger.info(f"Parsed time range - start_time param: {start_time} -> {start_dt}, end_time param: {end_time} -> {end_dt}")
        else:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=1)

        segments = playback_db.get_all_segments_in_range(start_dt, end_dt)

        # Filter out incomplete segments that are too small to be playable
        MIN_PLAYABLE_SIZE = 100 * 1024  # 100KB minimum
        for camera_id in list(segments.keys()):
            filtered = []
            for seg in segments[camera_id]:
                if seg.get('end_time') is None:
                    # Incomplete segment - check if it has enough data
                    seg_path = Path(seg['file_path'])
                    if seg_path.exists():
                        seg_size = seg_path.stat().st_size
                        if seg_size >= MIN_PLAYABLE_SIZE:
                            filtered.append(seg)
                        else:
                            logger.debug(f"Filtering out incomplete segment {seg['file_path']} ({seg_size} bytes)")
                else:
                    # Complete segment - include it
                    filtered.append(seg)
            segments[camera_id] = filtered

        # Check if we should query SD cards
        sd_card_config = config.get('sd_card_fallback', {})
        sd_card_enabled = sd_card_config.get('enabled', True)
        auto_fallback = sd_card_config.get('auto_fallback', True)

        sd_card_info = {}

        if sd_card_enabled and sd_card_manager:
            # Get cameras that might need SD card fallback
            cameras_needing_fallback = []

            if include_sd_card:
                # Query SD card for all supported cameras
                cameras_needing_fallback = sd_card_manager.get_supported_cameras()
            elif auto_fallback:
                # Only query SD card for cameras with no local recordings
                all_cameras = config.cameras
                for cam in all_cameras:
                    cam_id = cam.get('id')
                    if cam_id and cam_id not in segments:
                        cameras_needing_fallback.append(cam_id)

            # Query SD cards for cameras that need it
            for camera_id in cameras_needing_fallback:
                try:
                    sd_segments = await sd_card_manager.get_camera_sd_recordings(
                        camera_id, start_dt, end_dt
                    )
                    if sd_segments:
                        # Merge with existing segments for this camera
                        local_segs = segments.get(camera_id, [])
                        merged = sd_card_manager.merge_recordings(local_segs, sd_segments)
                        segments[camera_id] = merged
                        sd_card_info[camera_id] = len(sd_segments)
                        logger.info(f"Merged {len(sd_segments)} SD card recordings for {camera_id}")
                except Exception as e:
                    logger.warning(f"Failed to query SD card for {camera_id}: {e}")

        return {
            'start_time': start_dt.isoformat(),
            'end_time': end_dt.isoformat(),
            'cameras': segments,
            'sd_card_segments': sd_card_info if sd_card_info else None
        }

    except Exception as e:
        logger.error(f"Error getting recordings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/motion-events/{camera_id}")
async def get_camera_motion_events(
    camera_id: str,
    start_time: str = Query(..., description="ISO format datetime"),
    end_time: str = Query(..., description="ISO format datetime")
):
    """Get motion events for a camera in time range"""
    from nvr.web.api import playback_db

    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)

        events = playback_db.get_motion_events_in_range(camera_id, start_dt, end_dt)

        return {
            'camera_id': camera_id,
            'start_time': start_time,
            'end_time': end_time,
            'event_count': len(events),
            'events': events
        }

    except Exception as e:
        logger.error(f"Error getting motion events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/motion-events")
async def get_all_motion_events(
    start_time: str = Query(..., description="ISO format datetime"),
    end_time: str = Query(..., description="ISO format datetime"),
    aggregate: bool = Query(False, description="Return aggregated counts per 5-min bucket instead of individual events")
):
    """Get motion events for all cameras in time range"""
    from nvr.web.api import playback_db

    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)

        if aggregate:
            # Return aggregated counts per 5-minute bucket (much faster for timeline overview)
            buckets = playback_db.get_motion_event_counts(start_dt, end_dt, bucket_minutes=5)
            return {
                'start_time': start_time,
                'end_time': end_time,
                'aggregated': True,
                'bucket_minutes': 5,
                'cameras': buckets
            }
        else:
            events = playback_db.get_all_motion_events_in_range(start_dt, end_dt)
            return {
                'start_time': start_time,
                'end_time': end_time,
                'cameras': events
            }

    except Exception as e:
        logger.error(f"Error getting motion events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/video/{camera_id}")
async def stream_video_segment(
    camera_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    start_time: str = Query(..., description="ISO format datetime"),
    end_time: Optional[str] = Query(None, description="ISO format datetime"),
    speed: float = Query(1.0, description="Playback speed (1.0 = normal, 4.0 = 4x, 8.0 = 8x)"),
):
    """Stream video for a time range (may concatenate multiple segments).

    For speeds > 2x, uses server-side processing to create a truly sped-up video
    by using FFmpeg's setpts filter, which is much more efficient than relying
    on browser playbackRate for high speeds.
    """
    from nvr.web.api import playback_db, recorder_manager

    try:
        start_dt = datetime.fromisoformat(start_time)

        if end_time:
            end_dt = datetime.fromisoformat(end_time)
        else:
            # Default to 5 minutes
            end_dt = start_dt + timedelta(minutes=5)

        logger.info(f"VIDEO REQUEST - Camera: {camera_id}, start_time param: '{start_time}' -> {start_dt}, end_time param: '{end_time}' -> {end_dt}")

        # Get segments in range
        segments = playback_db.get_segments_in_range(camera_id, start_dt, end_dt)

        if not segments:
            logger.warning(f"No recordings found for {camera_id} between {start_dt} and {end_dt}")

            # Try to find the closest recording not earlier than start_dt
            logger.info(f"Looking for closest recording not earlier than {start_dt}")

            # Get all segments for this camera after start_dt
            all_segments = playback_db.get_all_segments(camera_id)

            # Filter to segments that start at or after the requested start time
            future_segments = [
                s for s in all_segments
                if datetime.fromisoformat(s['start_time']) >= start_dt
            ]

            if future_segments:
                # Sort by start time and get the earliest
                future_segments.sort(key=lambda s: s['start_time'])
                closest_segment = future_segments[0]
                closest_start = datetime.fromisoformat(closest_segment['start_time'])

                # Calculate duration that was requested
                requested_duration = (end_dt - start_dt).total_seconds()

                # Get segments from closest time for the same duration
                adjusted_end_dt = closest_start + timedelta(seconds=requested_duration)
                segments = playback_db.get_segments_in_range(camera_id, closest_start, adjusted_end_dt)

                if segments:
                    logger.info(f"Adjusted time range to {closest_start} - {adjusted_end_dt}, found {len(segments)} segment(s)")
                else:
                    raise HTTPException(status_code=404, detail=f"No recordings found for {camera_id} at or after {start_dt}")
            else:
                raise HTTPException(status_code=404, detail=f"No recordings found for {camera_id} at or after {start_dt}")

        logger.info(f"Found {len(segments)} segment(s) for {camera_id}")

        # Filter out segments whose files don't exist (deleted by retention policy)
        existing_segments = [s for s in segments if Path(s['file_path']).exists()]

        # Filter out incomplete segments (NULL end_time) that don't plausibly overlap with the request
        # An incomplete segment only makes sense if it started recently (within 10 minutes of request start)
        # This prevents serving "currently recording" segments from yesterday for a future date request
        MIN_PLAYABLE_SIZE = 100 * 1024  # 100KB minimum for a playable segment
        filtered_segments = []
        for seg in existing_segments:
            if seg['end_time'] is None:
                seg_start = datetime.fromisoformat(seg['start_time']) if isinstance(seg['start_time'], str) else seg['start_time']
                seg_path = Path(seg['file_path'])
                seg_size = seg_path.stat().st_size if seg_path.exists() else 0

                # Incomplete segments must have enough data to be playable
                if seg_size < MIN_PLAYABLE_SIZE:
                    logger.debug(f"Excluding incomplete segment {seg['file_path']} - too small ({seg_size} bytes)")
                    continue

                # For incomplete segments, only include if they started within a reasonable window of the request
                # or if the request start is within the segment's recording window (now)
                now = datetime.now()
                if seg_start <= start_dt <= now:
                    # Request start is between segment start and now - valid
                    filtered_segments.append(seg)
                elif start_dt > now:
                    # Request is for a future time - incomplete segments can't match
                    logger.debug(f"Excluding incomplete segment {seg['file_path']} - request is for future time {start_dt}")
                else:
                    filtered_segments.append(seg)
            else:
                # Completed segments - include them
                filtered_segments.append(seg)

        existing_segments = filtered_segments

        if not existing_segments:
            # Check if there are incomplete segments that were filtered out due to size
            incomplete_small_segments = [
                s for s in segments
                if s['end_time'] is None and Path(s['file_path']).exists()
                and Path(s['file_path']).stat().st_size < MIN_PLAYABLE_SIZE
            ]
            if incomplete_small_segments:
                logger.info(f"Recording in progress for {camera_id} but not enough data yet")
                raise HTTPException(
                    status_code=202,  # Accepted - recording in progress
                    detail=f"Recording in progress for {camera_id}. Please wait a few seconds and try again."
                )
            logger.warning(f"Database had {len(segments)} segments but none match the requested time range")
            raise HTTPException(status_code=404, detail=f"No recordings found for {camera_id} in the requested time range")

        logger.info(f"{len(existing_segments)} segment(s) exist on disk and match time range")

        # Serve segment(s) for the requested time range
        # Find the segment that best matches the requested start time
        if len(existing_segments) >= 1:
            # Find segment that contains the requested start time, or is closest after it
            # Prefer segments with non-NULL end_time (completed recordings)
            best_segment = None

            # First pass: look for completed segments only
            for seg in existing_segments:
                if not seg['end_time']:
                    continue  # Skip incomplete segments in first pass

                seg_start = datetime.fromisoformat(seg['start_time'])
                seg_end = datetime.fromisoformat(seg['end_time'])

                # If requested start is within this segment, use it
                if seg_start <= start_dt <= seg_end:
                    best_segment = seg
                    break
                # If requested start is before this segment starts, this is the next available
                elif start_dt < seg_start:
                    best_segment = seg
                    break

            # Second pass: if no completed segment found, consider incomplete ones
            if not best_segment:
                for seg in existing_segments:
                    seg_start = datetime.fromisoformat(seg['start_time'])

                    # For incomplete segments, check if start_time matches
                    if seg_start <= start_dt:
                        best_segment = seg
                        # Keep looking for a better match
                    elif start_dt < seg_start:
                        # This segment starts after requested time
                        if not best_segment:
                            best_segment = seg
                        break

            # If still no segment found, use the last one
            if not best_segment:
                best_segment = existing_segments[-1]

            segment_to_serve = best_segment
            file_path = Path(segment_to_serve['file_path'])

            if len(existing_segments) == 1:
                logger.info(f"Serving single segment: {file_path}")
            else:
                logger.info(f"Serving best matching segment (of {len(existing_segments)}): {file_path} (start: {segment_to_serve['start_time']})")

            # Check if file needs transcoding (mp4v -> H.264 for browser compatibility)
            probe_result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1',
                 str(file_path)],
                capture_output=True,
                text=True
            )
            codec = probe_result.stdout.strip()

            if codec == 'mpeg4':
                # Transcode mp4v to H.264 for browser compatibility
                logger.info(f"Transcoding {file_path.name} from mp4v to H.264 for browser")

                # First check if background transcoder already created the file (next to original)
                background_transcoded = file_path.parent / f"{file_path.stem}_h264{file_path.suffix}"

                if background_transcoded.exists():
                    logger.info(f"Using background-transcoded file: {background_transcoded.name}")
                    return range_requests_response(background_transcoded, request, content_type="video/mp4")

                # Fall back to on-demand transcoding
                # Create transcoded file in temp directory
                from nvr.core.config import config as nvr_config
                transcode_dir = nvr_config.storage_path / ".transcoded"
                transcode_dir.mkdir(exist_ok=True)

                transcoded_file = transcode_dir / f"{file_path.stem}_h264.mp4"

                # Check if already transcoded
                if not transcoded_file.exists():
                    logger.info(f"Creating transcoded file: {transcoded_file.name}")
                    transcode_cmd = [
                        'ffmpeg', '-i', str(file_path),
                        '-c:v', 'libx264',  # H.264 codec
                        '-preset', 'fast',  # Fast encoding
                        '-crf', '23',  # Quality (lower = better, 23 is default)
                        '-c:a', 'aac',  # AAC audio (if any)
                        '-movflags', '+faststart',  # Enable streaming
                        '-y',  # Overwrite
                        str(transcoded_file)
                    ]

                    result = subprocess.run(transcode_cmd, capture_output=True)
                    if result.returncode != 0:
                        logger.error(f"Transcode failed: {result.stderr.decode()}")
                        raise HTTPException(status_code=500, detail="Video transcode failed")

                    logger.info(f"Transcode complete: {transcoded_file.name}")
                else:
                    logger.info(f"Using cached transcoded file: {transcoded_file.name}")

                # Use transcoded file as the base for serving
                file_to_serve = transcoded_file
            else:
                # Already H.264 or other browser-compatible codec
                file_to_serve = file_path

            # Apply speed processing if requested (for speeds > 2x)
            if speed > 2.0:
                speed_file = get_speed_processed_video(file_to_serve, speed)
                if speed_file:
                    logger.info(f"Serving {speed}x speed-processed video: {speed_file.name}")
                    return range_requests_response(speed_file, request, content_type="video/mp4")
                else:
                    logger.warning(f"Speed processing failed, serving original at browser playbackRate")

            # Serve the file (original or transcoded)
            return range_requests_response(file_to_serve, request, content_type="video/mp4")

        # No segments found
        raise HTTPException(status_code=404, detail=f"No recordings found for {camera_id}")

    except ValueError as e:
        logger.error(f"Invalid datetime format: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming video for {camera_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/file")
async def serve_recording_file(file_path: str = Query(..., description="Absolute path to recording file")):
    """Serve a recording file directly by path"""
    try:
        path = Path(file_path)

        # Security check - ensure file is in recordings directory
        from nvr.web.api import recorder_manager
        from nvr.core.config import config as nvr_config
        storage_path = Path(recorder_manager.storage_path) if recorder_manager else nvr_config.storage_path

        try:
            # Resolve both paths and check if file is within storage
            resolved_file = path.resolve()
            resolved_storage = storage_path.resolve()

            if not str(resolved_file).startswith(str(resolved_storage)):
                raise HTTPException(status_code=403, detail="Access denied - file outside recordings directory")
        except Exception as e:
            logger.error(f"Path resolution error: {e}")
            raise HTTPException(status_code=403, detail="Invalid file path")

        if not path.exists():
            raise HTTPException(status_code=404, detail="Recording file not found")

        return FileResponse(
            path,
            media_type="video/mp4",
            filename=path.name
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/sd-card/{camera_id}")
async def stream_sd_card_recording(
    camera_id: str,
    background_tasks: BackgroundTasks,
    recording_token: str = Query(..., description="Recording token from SD card query"),
    start_time: Optional[str] = Query(None, description="Start time for playback (ISO format)")
):
    """
    Stream a recording from camera's SD card via ONVIF replay.

    This endpoint proxies the RTSP replay stream from the camera through
    FFmpeg to provide HTTP streaming to the browser.
    """
    from nvr.web.api import sd_card_manager
    from nvr.core.config import config

    try:
        # Check if SD card fallback is enabled
        sd_card_config = config.get('sd_card_fallback', {})
        if not sd_card_config.get('enabled', True):
            raise HTTPException(status_code=503, detail="SD card fallback is disabled")

        if not sd_card_manager:
            raise HTTPException(status_code=503, detail="SD card manager not initialized")

        # Get replay URI from camera
        replay_uri = await sd_card_manager.get_replay_uri(camera_id, recording_token)

        if not replay_uri:
            raise HTTPException(
                status_code=404,
                detail=f"Could not get replay URI for recording {recording_token}"
            )

        logger.info(f"Streaming SD card recording from {camera_id}: {recording_token}")

        # Build FFmpeg command to proxy RTSP to HTTP
        ffmpeg_cmd = [
            'ffmpeg',
            '-rtsp_transport', 'tcp',
            '-i', replay_uri,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-crf', '23',
            '-c:a', 'aac',
            '-movflags', 'frag_keyframe+empty_moov',
            '-f', 'mp4',
            'pipe:1'
        ]

        # If start_time specified, add seek option
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time)
                # Calculate offset - would need recording start time
                # For now, just use the start_time as-is
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-rtsp_transport', 'tcp',
                    '-i', replay_uri,
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-tune', 'zerolatency',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-movflags', 'frag_keyframe+empty_moov',
                    '-f', 'mp4',
                    'pipe:1'
                ]
            except ValueError:
                pass  # Ignore invalid start_time

        # Start FFmpeg process
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10485760  # 10MB buffer
        )

        # Register cleanup
        def cleanup_process():
            try:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                logger.info(f"Cleaned up SD card streaming process for {camera_id}")
            except Exception as e:
                logger.error(f"Error cleaning up SD card stream process: {e}")

        background_tasks.add_task(cleanup_process)

        # Generator to stream FFmpeg output
        def stream_sd_card():
            try:
                while True:
                    chunk = process.stdout.read(65536)  # 64KB chunks
                    if not chunk:
                        break
                    yield chunk

                # Check for errors
                process.wait()
                if process.returncode != 0:
                    stderr = process.stderr.read().decode('utf-8')
                    logger.error(f"FFmpeg SD card streaming error: {stderr[-500:]}")
            except Exception as e:
                logger.error(f"Error in SD card stream generator: {e}")
            finally:
                if process.poll() is None:
                    process.terminate()

        return StreamingResponse(
            stream_sd_card(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'inline; filename="{camera_id}_sd_card.mp4"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming SD card recording: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/sd-card-status")
async def get_sd_card_status():
    """Get SD card fallback status and supported cameras."""
    from nvr.web.api import sd_card_manager
    from nvr.core.config import config

    try:
        sd_card_config = config.get('sd_card_fallback', {})
        enabled = sd_card_config.get('enabled', True)

        if not sd_card_manager:
            return {
                'enabled': enabled,
                'initialized': False,
                'supported_cameras': [],
                'message': 'SD card manager not initialized'
            }

        supported = sd_card_manager.get_supported_cameras()

        return {
            'enabled': enabled,
            'initialized': True,
            'auto_fallback': sd_card_config.get('auto_fallback', True),
            'cache_duration_seconds': sd_card_config.get('cache_duration_seconds', 300),
            'supported_cameras': supported,
            'message': f'{len(supported)} camera(s) support SD card fallback'
        }

    except Exception as e:
        logger.error(f"Error getting SD card status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _concatenate_segments(camera_id: str, segments: List[dict], start_dt: datetime, background_tasks: BackgroundTasks):
    """Concatenate multiple video segments using ffmpeg with streaming output"""
    try:
        # Create temporary file list for ffmpeg concat
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            list_file = f.name
            for segment in segments:
                file_path = Path(segment['file_path'])
                if file_path.exists():
                    f.write(f"file '{file_path.absolute()}'\n")

        # Stream concatenation: output to pipe instead of file
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file,
            '-c', 'copy',
            '-movflags', 'frag_keyframe+empty_moov',  # Enable streaming-friendly format
            '-f', 'mp4',
            'pipe:1'  # Output to stdout
        ]

        logger.info(f"Starting streaming concatenation for {camera_id} ({len(segments)} segments)")

        # Start ffmpeg process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10485760  # 10MB buffer
        )

        # Register cleanup
        def cleanup_process():
            try:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                os.unlink(list_file)
                logger.info(f"Cleaned up streaming process for {camera_id}")
            except Exception as e:
                logger.error(f"Error cleaning up process: {e}")

        background_tasks.add_task(cleanup_process)

        # Generator to stream ffmpeg output
        def stream_video():
            try:
                while True:
                    chunk = process.stdout.read(65536)  # 64KB chunks
                    if not chunk:
                        break
                    yield chunk

                # Check for errors
                process.wait()
                if process.returncode != 0:
                    stderr = process.stderr.read().decode('utf-8')
                    logger.error(f"ffmpeg streaming error: {stderr[-500:]}")
            except Exception as e:
                logger.error(f"Error in stream_video generator: {e}")
            finally:
                if process.poll() is None:
                    process.terminate()

        # Return streaming response
        return StreamingResponse(
            stream_video(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'inline; filename="{camera_id}_{start_dt.strftime("%Y%m%d_%H%M%S")}.mp4"'
            }
        )

    except Exception as e:
        logger.error(f"Error setting up streaming concatenation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/available-dates/{camera_id}")
async def get_available_dates(camera_id: str):
    """Get list of dates that have recordings for a camera"""
    from nvr.web.api import playback_db

    try:
        dates = playback_db.get_recording_days(camera_id)
        return {
            'camera_id': camera_id,
            'dates': dates
        }

    except Exception as e:
        logger.error(f"Error getting available dates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/storage-stats")
async def get_storage_stats():
    """Get storage statistics"""
    from nvr.web.api import playback_db

    try:
        stats = playback_db.get_storage_stats()
        return stats

    except Exception as e:
        logger.error(f"Error getting storage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/playback/export")
async def export_clip(request: PlaybackRequest):
    """Export a video clip for a specific time range"""
    from nvr.web.api import playback_db

    try:
        start_dt = datetime.fromisoformat(request.start_time)

        if request.end_time:
            end_dt = datetime.fromisoformat(request.end_time)
        else:
            end_dt = start_dt + timedelta(minutes=5)

        # Get segments
        segments = playback_db.get_segments_in_range(
            request.camera_id,
            start_dt,
            end_dt
        )

        if not segments:
            raise HTTPException(status_code=404, detail="No recordings found")

        # Use the stream endpoint to get the video
        return await stream_video_segment(
            request.camera_id,
            request.start_time,
            request.end_time
        )

    except Exception as e:
        logger.error(f"Error exporting clip: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Bookmark Endpoints =====

class BookmarkCreate(BaseModel):
    camera_id: str
    timestamp: datetime
    label: Optional[str] = None
    notes: Optional[str] = None
    color: str = '#ff9500'


class BookmarkUpdate(BaseModel):
    label: Optional[str] = None
    notes: Optional[str] = None
    color: Optional[str] = None


@router.post("/api/playback/bookmarks")
async def create_bookmark(bookmark: BookmarkCreate):
    """Create a new bookmark at a specific timestamp"""
    try:
        from nvr.web.api import playback_db

        if not playback_db:
            raise HTTPException(status_code=503, detail="Database not initialized")

        bookmark_id = playback_db.add_bookmark(
            camera_id=bookmark.camera_id,
            timestamp=bookmark.timestamp,
            label=bookmark.label,
            notes=bookmark.notes,
            color=bookmark.color
        )

        return {
            "success": True,
            "bookmark_id": bookmark_id,
            "message": "Bookmark created"
        }

    except Exception as e:
        logger.error(f"Error creating bookmark: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/bookmarks")
async def get_bookmarks(
    camera_id: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None)
):
    """Get bookmarks for a camera or all cameras in a time range"""
    try:
        from nvr.web.api import playback_db

        if not playback_db:
            raise HTTPException(status_code=503, detail="Database not initialized")

        # Default to last 24 hours if no time range specified
        if not start_time:
            start_time = datetime.now() - timedelta(days=1)
        if not end_time:
            end_time = datetime.now()

        if camera_id:
            bookmarks = playback_db.get_bookmarks_in_range(
                camera_id=camera_id,
                start_time=start_time,
                end_time=end_time
            )
        else:
            bookmarks = playback_db.get_all_bookmarks_in_range(
                start_time=start_time,
                end_time=end_time
            )

        return {"bookmarks": bookmarks}

    except Exception as e:
        logger.error(f"Error fetching bookmarks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/playback/bookmarks/{bookmark_id}")
async def update_bookmark(bookmark_id: int, update: BookmarkUpdate):
    """Update an existing bookmark"""
    try:
        from nvr.web.api import playback_db

        if not playback_db:
            raise HTTPException(status_code=503, detail="Database not initialized")

        success = playback_db.update_bookmark(
            bookmark_id=bookmark_id,
            label=update.label,
            notes=update.notes,
            color=update.color
        )

        if not success:
            raise HTTPException(status_code=404, detail="Bookmark not found")

        return {
            "success": True,
            "message": "Bookmark updated"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating bookmark: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/playback/bookmarks/{bookmark_id}")
async def delete_bookmark(bookmark_id: int):
    """Delete a bookmark"""
    try:
        from nvr.web.api import playback_db

        if not playback_db:
            raise HTTPException(status_code=503, detail="Database not initialized")

        success = playback_db.delete_bookmark(bookmark_id)

        if not success:
            raise HTTPException(status_code=404, detail="Bookmark not found")

        return {
            "success": True,
            "message": "Bookmark deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting bookmark: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SD Card Recording Access (ONVIF Profile G)
# ============================================================================

@router.get("/api/playback/sd-card/check/{camera_id}")
async def check_sd_card_recordings(
    camera_id: str,
    start_time: str = Query(..., description="ISO format datetime"),
    end_time: str = Query(..., description="ISO format datetime")
):
    """
    Check if camera's SD card has recordings for the specified time range.

    This queries the camera via ONVIF Profile G to find recordings that might
    fill gaps in local storage.
    """
    from nvr.web.api import config
    from nvr.core.onvif_discovery import ONVIFDevice

    try:
        # Find camera config
        camera_config = None
        for cam in config.cameras:
            if cam.get('id') == camera_id or cam.get('name') == camera_id:
                camera_config = cam
                break

        if not camera_config:
            raise HTTPException(status_code=404, detail=f"Camera not found: {camera_id}")

        # Check if camera has ONVIF config
        onvif_host = camera_config.get('onvif_host')
        if not onvif_host:
            return {
                "success": False,
                "error": "Camera does not have ONVIF configuration",
                "supports_sd_card": False,
                "recordings": []
            }

        onvif_port = camera_config.get('onvif_port', 8089)
        username = camera_config.get('username', 'admin')
        password = camera_config.get('password', 'admin')

        # Parse time range
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)

        # Connect to camera via ONVIF
        device = ONVIFDevice(onvif_host, onvif_port, username, password)

        connected = await device.connect()
        if not connected:
            return {
                "success": False,
                "error": "Could not connect to camera via ONVIF",
                "supports_sd_card": False,
                "recordings": []
            }

        # Check Profile G support
        supports_profile_g = await device.check_profile_g_support()
        if not supports_profile_g:
            return {
                "success": True,
                "supports_sd_card": False,
                "message": "Camera does not support SD card access (Profile G)",
                "recordings": []
            }

        # Get SD card recordings
        recordings = await device.get_sd_recordings(start_dt, end_dt)

        return {
            "success": True,
            "supports_sd_card": True,
            "camera_id": camera_id,
            "recordings": recordings
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking SD card for {camera_id}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "supports_sd_card": False,
            "recordings": []
        }


@router.get("/api/playback/sd-card-gaps")
async def check_sd_card_for_gaps(
    start_time: str = Query(..., description="ISO format datetime"),
    end_time: str = Query(..., description="ISO format datetime"),
    cameras: str = Query(None, description="Comma-separated camera IDs (optional, checks all if not specified)")
):
    """
    Check SD cards for recordings that could fill gaps in local storage.

    Returns a list of SD card recordings that exist where local storage has gaps.
    """
    from nvr.web.api import config, playback_db
    from nvr.core.onvif_discovery import ONVIFDevice

    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)

        # Determine which cameras to check
        camera_list = cameras.split(',') if cameras else [c.get('id') or c['name'] for c in config.cameras]

        results = {}

        for camera_id in camera_list:
            camera_id = camera_id.strip()

            # Find camera config
            camera_config = None
            for cam in config.cameras:
                if cam.get('id') == camera_id or cam.get('name') == camera_id:
                    camera_config = cam
                    break

            if not camera_config:
                results[camera_id] = {"error": "Camera not found", "sd_recordings": []}
                continue

            # Get local recordings
            local_segments = playback_db.get_segments_in_range(camera_id, start_dt, end_dt) if playback_db else []

            # Find gaps in local recordings
            gaps = find_gaps_in_segments(local_segments, start_dt, end_dt)

            if not gaps:
                results[camera_id] = {
                    "has_gaps": False,
                    "gap_count": 0,
                    "sd_recordings": []
                }
                continue

            # Check if camera has ONVIF config
            onvif_host = camera_config.get('onvif_host')
            if not onvif_host:
                results[camera_id] = {
                    "has_gaps": True,
                    "gap_count": len(gaps),
                    "gaps": gaps,
                    "sd_recordings": [],
                    "error": "No ONVIF configuration"
                }
                continue

            # Connect to camera and check SD card
            try:
                device = ONVIFDevice(
                    onvif_host,
                    camera_config.get('onvif_port', 8089),
                    camera_config.get('username', 'admin'),
                    camera_config.get('password', 'admin')
                )

                connected = await device.connect()
                if not connected:
                    results[camera_id] = {
                        "has_gaps": True,
                        "gap_count": len(gaps),
                        "gaps": gaps,
                        "sd_recordings": [],
                        "error": "Could not connect via ONVIF"
                    }
                    continue

                supports_profile_g = await device.check_profile_g_support()
                if not supports_profile_g:
                    results[camera_id] = {
                        "has_gaps": True,
                        "gap_count": len(gaps),
                        "gaps": gaps,
                        "sd_recordings": [],
                        "supports_sd_card": False
                    }
                    continue

                # Get SD recordings
                sd_recordings = await device.get_sd_recordings(start_dt, end_dt)

                # Filter SD recordings to only those that fill gaps
                gap_filling_recordings = []
                for sd_rec in sd_recordings:
                    sd_start = datetime.fromisoformat(sd_rec['start_time'].replace('Z', '+00:00'))
                    sd_end = datetime.fromisoformat(sd_rec['end_time'].replace('Z', '+00:00'))

                    for gap in gaps:
                        gap_start = datetime.fromisoformat(gap['start_time'])
                        gap_end = datetime.fromisoformat(gap['end_time'])

                        # Check if SD recording overlaps with gap
                        if sd_start < gap_end and sd_end > gap_start:
                            gap_filling_recordings.append({
                                **sd_rec,
                                'fills_gap': {
                                    'start': gap['start_time'],
                                    'end': gap['end_time']
                                }
                            })
                            break

                results[camera_id] = {
                    "has_gaps": True,
                    "gap_count": len(gaps),
                    "gaps": gaps,
                    "sd_recordings": gap_filling_recordings,
                    "supports_sd_card": True
                }

            except Exception as e:
                logger.error(f"Error checking SD card for {camera_id}: {e}")
                results[camera_id] = {
                    "has_gaps": True,
                    "gap_count": len(gaps),
                    "gaps": gaps,
                    "sd_recordings": [],
                    "error": str(e)
                }

        return {
            "success": True,
            "start_time": start_time,
            "end_time": end_time,
            "cameras": results
        }

    except Exception as e:
        logger.error(f"Error checking SD cards for gaps: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def find_gaps_in_segments(segments: List[Dict], start_dt: datetime, end_dt: datetime) -> List[Dict]:
    """Find gaps in a list of recording segments within a time range."""
    if not segments:
        # Entire range is a gap
        return [{
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "duration_seconds": (end_dt - start_dt).total_seconds()
        }]

    def parse_time(value, default: datetime = None) -> Optional[datetime]:
        """Parse time value - handles strings, datetime objects, and None"""
        if value is None:
            return default
        if isinstance(value, datetime):
            return value
        value_str = str(value)
        if value_str == 'None' or not value_str:
            return default
        return datetime.fromisoformat(value_str)

    # Filter segments to only those with valid start and end times
    valid_segments = []
    for seg in segments:
        start = parse_time(seg.get('start_time'))
        end = parse_time(seg.get('end_time'))
        if start is not None and end is not None:
            valid_segments.append(seg)

    if not valid_segments:
        return [{
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "duration_seconds": (end_dt - start_dt).total_seconds()
        }]

    segments = valid_segments

    gaps = []

    # Sort segments by start time
    sorted_segments = sorted(segments, key=lambda s: parse_time(s['start_time']))

    # Check for gap at the beginning
    first_start = parse_time(sorted_segments[0]['start_time'])
    if first_start > start_dt:
        gap_duration = (first_start - start_dt).total_seconds()
        if gap_duration > 60:  # Only count gaps > 1 minute
            gaps.append({
                "start_time": start_dt.isoformat(),
                "end_time": first_start.isoformat(),
                "duration_seconds": gap_duration
            })

    # Check for gaps between segments
    for i in range(len(sorted_segments) - 1):
        current_end = parse_time(sorted_segments[i]['end_time'])
        next_start = parse_time(sorted_segments[i + 1]['start_time'])

        if next_start > current_end:
            gap_duration = (next_start - current_end).total_seconds()
            if gap_duration > 60:  # Only count gaps > 1 minute
                gaps.append({
                    "start_time": current_end.isoformat(),
                    "end_time": next_start.isoformat(),
                    "duration_seconds": gap_duration
                })

    # Check for gap at the end
    last_end = parse_time(sorted_segments[-1]['end_time'])
    if last_end < end_dt:
        gap_duration = (end_dt - last_end).total_seconds()
        if gap_duration > 60:  # Only count gaps > 1 minute
            gaps.append({
                "start_time": last_end.isoformat(),
                "end_time": end_dt.isoformat(),
                "duration_seconds": gap_duration
            })

    return gaps
