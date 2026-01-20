"""Playback API endpoints for video archive access"""

from fastapi import APIRouter, HTTPException, Query, Response, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import logging
import subprocess
import tempfile
import os

logger = logging.getLogger(__name__)


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
    camera_name: str
    start_time: str  # ISO format datetime
    end_time: Optional[str] = None  # ISO format datetime
    speed: float = 1.0


class TimeRangeRequest(BaseModel):
    """Request for time range query"""
    start_time: str
    end_time: str
    cameras: Optional[List[str]] = None


@router.get("/api/playback/recordings/{camera_name}")
async def get_camera_recordings(
    camera_name: str,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    start_time: Optional[str] = Query(None, description="ISO format datetime"),
    end_time: Optional[str] = Query(None, description="ISO format datetime")
):
    """Get list of recording segments for a camera"""
    from nvr.web.api import playback_db

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

        segments = playback_db.get_segments_in_range(camera_name, start_dt, end_dt)

        return {
            'camera_name': camera_name,
            'start_time': start_dt.isoformat(),
            'end_time': end_dt.isoformat(),
            'segment_count': len(segments),
            'segments': segments
        }

    except Exception as e:
        logger.error(f"Error getting recordings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/recordings")
async def get_all_recordings(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    start_time: Optional[str] = Query(None, description="ISO format datetime"),
    end_time: Optional[str] = Query(None, description="ISO format datetime")
):
    """Get recording segments for all cameras"""
    from nvr.web.api import playback_db

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

        return {
            'start_time': start_dt.isoformat(),
            'end_time': end_dt.isoformat(),
            'cameras': segments
        }

    except Exception as e:
        logger.error(f"Error getting recordings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/motion-events/{camera_name}")
async def get_camera_motion_events(
    camera_name: str,
    start_time: str = Query(..., description="ISO format datetime"),
    end_time: str = Query(..., description="ISO format datetime")
):
    """Get motion events for a camera in time range"""
    from nvr.web.api import playback_db

    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)

        events = playback_db.get_motion_events_in_range(camera_name, start_dt, end_dt)

        return {
            'camera_name': camera_name,
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
    end_time: str = Query(..., description="ISO format datetime")
):
    """Get motion events for all cameras in time range"""
    from nvr.web.api import playback_db

    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)

        events = playback_db.get_all_motion_events_in_range(start_dt, end_dt)

        return {
            'start_time': start_time,
            'end_time': end_time,
            'cameras': events
        }

    except Exception as e:
        logger.error(f"Error getting motion events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/video/{camera_name}")
async def stream_video_segment(
    camera_name: str,
    request: Request,
    background_tasks: BackgroundTasks,
    start_time: str = Query(..., description="ISO format datetime"),
    end_time: Optional[str] = Query(None, description="ISO format datetime"),
):
    """Stream video for a time range (may concatenate multiple segments)"""
    from nvr.web.api import playback_db, recorder_manager

    try:
        start_dt = datetime.fromisoformat(start_time)

        if end_time:
            end_dt = datetime.fromisoformat(end_time)
        else:
            # Default to 5 minutes
            end_dt = start_dt + timedelta(minutes=5)

        logger.info(f"VIDEO REQUEST - Camera: {camera_name}, start_time param: '{start_time}' -> {start_dt}, end_time param: '{end_time}' -> {end_dt}")

        # Get segments in range
        segments = playback_db.get_segments_in_range(camera_name, start_dt, end_dt)

        if not segments:
            logger.warning(f"No recordings found for {camera_name} between {start_dt} and {end_dt}")

            # Try to find the closest recording not earlier than start_dt
            logger.info(f"Looking for closest recording not earlier than {start_dt}")

            # Get all segments for this camera after start_dt
            all_segments = playback_db.get_all_segments(camera_name)

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
                segments = playback_db.get_segments_in_range(camera_name, closest_start, adjusted_end_dt)

                if segments:
                    logger.info(f"Adjusted time range to {closest_start} - {adjusted_end_dt}, found {len(segments)} segment(s)")
                else:
                    raise HTTPException(status_code=404, detail=f"No recordings found for {camera_name} at or after {start_dt}")
            else:
                raise HTTPException(status_code=404, detail=f"No recordings found for {camera_name} at or after {start_dt}")

        logger.info(f"Found {len(segments)} segment(s) for {camera_name}")

        # Filter out segments whose files don't exist (deleted by retention policy)
        existing_segments = [s for s in segments if Path(s['file_path']).exists()]

        if not existing_segments:
            logger.warning(f"Database had {len(segments)} segments but none exist on disk")
            raise HTTPException(status_code=404, detail=f"No recordings found for {camera_name} (files deleted)")

        logger.info(f"{len(existing_segments)} segment(s) exist on disk")

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
                transcode_dir = Path("recordings/.transcoded")
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

                # Serve transcoded file
                return range_requests_response(transcoded_file, request, content_type="video/mp4")
            else:
                # Already H.264 or other browser-compatible codec, serve directly
                return range_requests_response(file_path, request, content_type="video/mp4")

        # No segments found
        raise HTTPException(status_code=404, detail=f"No recordings found for {camera_name}")

    except ValueError as e:
        logger.error(f"Invalid datetime format: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming video for {camera_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/file")
async def serve_recording_file(file_path: str = Query(..., description="Absolute path to recording file")):
    """Serve a recording file directly by path"""
    try:
        path = Path(file_path)

        # Security check - ensure file is in recordings directory
        from nvr.web.api import recorder_manager
        storage_path = Path(recorder_manager.storage_path) if recorder_manager else Path("./recordings")

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


async def _concatenate_segments(camera_name: str, segments: List[dict], start_dt: datetime, background_tasks: BackgroundTasks):
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

        logger.info(f"Starting streaming concatenation for {camera_name} ({len(segments)} segments)")

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
                logger.info(f"Cleaned up streaming process for {camera_name}")
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
                "Content-Disposition": f'inline; filename="{camera_name}_{start_dt.strftime("%Y%m%d_%H%M%S")}.mp4"'
            }
        )

    except Exception as e:
        logger.error(f"Error setting up streaming concatenation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playback/available-dates/{camera_name}")
async def get_available_dates(camera_name: str):
    """Get list of dates that have recordings for a camera"""
    from nvr.web.api import playback_db

    try:
        dates = playback_db.get_recording_days(camera_name)
        return {
            'camera_name': camera_name,
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
            request.camera_name,
            start_dt,
            end_dt
        )

        if not segments:
            raise HTTPException(status_code=404, detail="No recordings found")

        # Use the stream endpoint to get the video
        return await stream_video_segment(
            request.camera_name,
            request.start_time,
            request.end_time
        )

    except Exception as e:
        logger.error(f"Error exporting clip: {e}")
        raise HTTPException(status_code=500, detail=str(e))
