"""Playback API endpoints for video archive access"""

from fastapi import APIRouter, HTTPException, Query, Response
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

        # Get segments in range
        segments = playback_db.get_segments_in_range(camera_name, start_dt, end_dt)

        if not segments:
            logger.warning(f"No recordings found for {camera_name} between {start_dt} and {end_dt}")
            raise HTTPException(status_code=404, detail=f"No recordings found for {camera_name} in the specified time range")

        logger.info(f"Found {len(segments)} segment(s) for {camera_name}")

        # If single segment, return it directly
        if len(segments) == 1:
            file_path = Path(segments[0]['file_path'])
            logger.info(f"Serving single segment: {file_path}")

            if not file_path.exists():
                logger.error(f"Recording file not found: {file_path}")
                raise HTTPException(status_code=404, detail=f"Recording file not found: {file_path}")

            return FileResponse(
                file_path,
                media_type="video/mp4",
                filename=f"{camera_name}_{start_dt.strftime('%Y%m%d_%H%M%S')}.mp4"
            )

        # Multiple segments - concatenate using ffmpeg
        logger.info(f"Concatenating {len(segments)} segments for {camera_name}")
        return await _concatenate_segments(camera_name, segments, start_dt)

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


async def _concatenate_segments(camera_name: str, segments: List[dict], start_dt: datetime):
    """Concatenate multiple video segments using ffmpeg"""
    try:
        # Create temporary file list for ffmpeg concat
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            list_file = f.name
            for segment in segments:
                file_path = Path(segment['file_path'])
                if file_path.exists():
                    f.write(f"file '{file_path.absolute()}'\n")

        # Output file
        output_file = tempfile.NamedTemporaryFile(
            suffix='.mp4',
            delete=False,
            prefix=f"{camera_name}_{start_dt.strftime('%Y%m%d_%H%M%S')}_"
        )
        output_path = output_file.name
        output_file.close()

        # Run ffmpeg to concatenate
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file,
            '-c', 'copy',
            '-y',
            output_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        # Clean up list file
        os.unlink(list_file)

        if result.returncode != 0:
            logger.error(f"ffmpeg returncode: {result.returncode}")
            logger.error(f"ffmpeg stderr (last 500 chars): {result.stderr[-500:]}")
            logger.error(f"ffmpeg stdout: {result.stdout}")
            logger.error(f"ffmpeg command: {' '.join(cmd)}")
            raise Exception(f"Failed to concatenate video segments (returncode: {result.returncode})")

        # Return the concatenated file and schedule cleanup
        def cleanup():
            try:
                os.unlink(output_path)
            except:
                pass

        return FileResponse(
            output_path,
            media_type="video/mp4",
            filename=f"{camera_name}_{start_dt.strftime('%Y%m%d_%H%M%S')}.mp4",
            background=cleanup
        )

    except Exception as e:
        logger.error(f"Error concatenating segments: {e}")
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
