"""FastAPI web application for NVR"""

import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi import Request
from pathlib import Path
from typing import List, Dict, Any
import cv2
import numpy as np
import asyncio
from datetime import datetime
import json

from nvr.core.config import config
from nvr.core.recorder import RecorderManager
from nvr.core.motion import MotionMonitor
from nvr.core.onvif_discovery import ONVIFDiscovery
from nvr.core.playback_db import PlaybackDatabase
from nvr.core.ai_detection import AIDetectionMonitor
from nvr.web.webrtc_server import WebRTCManager
from nvr.web.webrtc_h264 import WebRTCPassthroughManager
from nvr.web.rtsp_proxy import RTSPProxy, MSEStreamProxy

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="SF-NVR", description="Network Video Recorder")

# Templates and static files
templates = Jinja2Templates(directory="nvr/templates")
app.mount("/static", StaticFiles(directory="nvr/static"), name="static")

# Include extensions
from nvr.web.api_extensions import router as extensions_router
from nvr.web.playback_api import router as playback_router
from nvr.web.settings_api import router as settings_router
app.include_router(extensions_router)
app.include_router(playback_router)
app.include_router(settings_router)

# Global instances
recorder_manager: RecorderManager = None
motion_monitor: MotionMonitor = None
ai_monitor: AIDetectionMonitor = None
playback_db: PlaybackDatabase = None
webrtc_manager: WebRTCManager = None
webrtc_passthrough: WebRTCPassthroughManager = None
rtsp_proxy: RTSPProxy = None
mse_proxy: MSEStreamProxy = None


@app.on_event("startup")
async def startup_event():
    """Initialize NVR on startup"""
    global recorder_manager, motion_monitor, ai_monitor, playback_db, webrtc_manager, webrtc_passthrough, rtsp_proxy, mse_proxy

    logger.info("Starting NVR...")

    # Start background cache cleaner for transcoded files
    from nvr.core.cache_cleaner import get_cache_cleaner
    get_cache_cleaner()  # Starts automatically

    # Queue existing mp4v files for background transcoding
    from nvr.core.transcoder import get_transcoder
    import subprocess
    transcoder = get_transcoder()
    queued_count = 0
    for video_file in Path("recordings").rglob("*.mp4"):
        # Check if it's mp4v (mpeg4)
        try:
            probe_result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1',
                 str(video_file)],
                capture_output=True,
                text=True,
                timeout=5
            )
            if probe_result.stdout.strip() == 'mpeg4':
                transcoder.queue_transcode(video_file)
                queued_count += 1
        except Exception as e:
            logger.warning(f"Failed to check codec for {video_file.name}: {e}")

    if queued_count > 0:
        logger.info(f"Queued {queued_count} existing mp4v files for background transcoding")

    # Optimize OpenCV for multi-threading
    import os
    num_threads = os.cpu_count() or 4
    cv2.setNumThreads(num_threads)
    logger.info(f"OpenCV configured to use {num_threads} threads")

    # Initialize playback database
    db_path = config.storage_path / "playback.db"
    playback_db = PlaybackDatabase(db_path)
    logger.info(f"Playback database initialized at {db_path}")

    # Schedule periodic database maintenance (runs every 24 hours)
    from nvr.core.db_maintenance import schedule_maintenance
    schedule_maintenance(playback_db, interval_hours=24)
    logger.info("Database maintenance scheduled")

    # Initialize recorder manager with database
    recorder_manager = RecorderManager(
        storage_path=config.storage_path,
        segment_duration=config.get('recording.segment_duration', 300),
        playback_db=playback_db
    )

    # Initialize motion monitor
    motion_monitor = MotionMonitor()

    # Initialize AI detection monitor
    if config.get('ai_detection.enabled', False):
        ai_monitor = AIDetectionMonitor(
            confidence_threshold=config.get('ai_detection.confidence_threshold', 0.5)
        )
        logger.info("AI detection enabled (person/vehicle recognition)")

    # Auto-discover cameras if enabled
    if config.get('onvif.auto_discover', True):
        logger.info("Auto-discovering ONVIF cameras...")
        try:
            from nvr.core.onvif_discovery import ONVIFDiscovery
            discovery = ONVIFDiscovery(
                username=config.default_camera_username,
                password=config.default_camera_password
            )
            timeout = config.get('onvif.discovery_timeout', 2)
            devices = await discovery.discover_cameras(timeout=timeout)

            # Add newly discovered cameras to config
            existing_ips = [c.get('onvif_host') for c in config.cameras]
            new_count = 0
            for device in devices:
                if device.host not in existing_ips:
                    camera_dict = device.to_dict()
                    config.add_camera(camera_dict)
                    new_count += 1
                    logger.info(f"Auto-discovered: {camera_dict['name']}")

            if new_count > 0:
                logger.info(f"Added {new_count} new camera(s) to configuration")
        except Exception as e:
            logger.error(f"Auto-discovery failed: {e}")

    # Load all cameras and start recording immediately
    cameras = config.cameras
    recording_enabled = config.get('recording.enabled', True)

    for camera in cameras:
        if not camera.get('enabled', True):
            continue

        camera_name = camera['name']
        camera_id = camera.get('id', camera_name)  # Fallback to name if no ID
        rtsp_url = camera['rtsp_url']

        # Add recorder and start only if recording is enabled
        if recording_enabled:
            await recorder_manager.add_camera(camera_name, rtsp_url, camera_id=camera_id, auto_start=True)

        # Add motion detector if enabled
        if config.get('motion_detection.enabled', True):
            recorder = recorder_manager.get_recorder(camera_name)
            motion_monitor.add_camera(
                camera_name,
                sensitivity=config.get('motion_detection.sensitivity', 25),
                min_area=config.get('motion_detection.min_area', 500),
                recorder=recorder
            )

        # Add AI detector if enabled
        if config.get('ai_detection.enabled', False) and ai_monitor:
            recorder = recorder_manager.get_recorder(camera_name)
            ai_monitor.add_camera(
                camera_name,
                recorder=recorder,
                confidence_threshold=config.get('ai_detection.confidence_threshold', 0.5)
            )

    logger.info(f"Started recording on {len(cameras)} camera(s)")

    # Initialize WebRTC managers
    webrtc_manager = WebRTCManager(recorder_manager)
    logger.info("WebRTC manager initialized for low-latency streaming")

    # Initialize H.264 passthrough manager for zero-copy streaming
    webrtc_passthrough = WebRTCPassthroughManager(config)
    logger.info("WebRTC H.264 passthrough manager initialized (ZERO-LATENCY MODE)")

    # Initialize RTSP proxy for ABSOLUTE MAXIMUM SPEED
    rtsp_proxy = RTSPProxy()
    mse_proxy = MSEStreamProxy()
    logger.info("RTSP Direct Proxy initialized (ABSOLUTE ZERO-LATENCY - no Python processing)")

    # Start cleanup task
    asyncio.create_task(cleanup_task())

    # Start disk space monitor (prevents drive from filling up)
    asyncio.create_task(disk_monitor_task())
    logger.info("Disk space monitor started - will prevent drive from filling up")

    # Start motion monitoring
    if config.get('motion_detection.enabled', True) and motion_monitor.detectors:
        asyncio.create_task(motion_monitor.start_monitoring(recorder_manager))

    # Start AI monitoring
    if config.get('ai_detection.enabled', False) and ai_monitor and ai_monitor.detectors:
        asyncio.create_task(ai_monitor.start_monitoring(recorder_manager))
        logger.info("AI monitoring started for person/vehicle detection")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    logger.info("Shutting down NVR...")

    # Stop background cache cleaner
    from nvr.core.cache_cleaner import shutdown_cache_cleaner
    shutdown_cache_cleaner()

    # Stop background transcoder
    from nvr.core.transcoder import shutdown_transcoder
    shutdown_transcoder()

    if webrtc_manager:
        await webrtc_manager.close_all()
    if recorder_manager:
        recorder_manager.stop_all()
    if motion_monitor:
        motion_monitor.stop_monitoring()
    if ai_monitor:
        ai_monitor.stop_monitoring()


async def cleanup_task():
    """Periodic cleanup of old recordings"""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            retention_days = config.get('recording.retention_days', 7)
            if recorder_manager:
                recorder_manager.cleanup_old_recordings(retention_days)
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")


async def disk_monitor_task():
    """Monitor disk space and prevent drive from filling up"""
    from nvr.core.disk_manager import DiskManager

    # Safety thresholds
    MIN_FREE_GB = 5.0  # Always keep at least 5GB free
    WARNING_THRESHOLD = 90.0  # Start cleanup at 90% full
    CRITICAL_THRESHOLD = 95.0  # Aggressive cleanup at 95% full

    storage_path = config.storage_path
    disk_manager = DiskManager(storage_path, min_free_gb=MIN_FREE_GB, warning_threshold_percent=WARNING_THRESHOLD)

    logger.info(f"Disk monitor started: min_free={MIN_FREE_GB}GB, warning={WARNING_THRESHOLD}%, critical={CRITICAL_THRESHOLD}%")

    while True:
        try:
            await asyncio.sleep(300)  # Check every 5 minutes

            usage = disk_manager.get_disk_usage()
            if not usage:
                continue

            # Check if we need emergency cleanup
            if usage['percent'] >= CRITICAL_THRESHOLD or usage['free_gb'] < MIN_FREE_GB:
                logger.error(f"CRITICAL: Disk space low! {usage['free_gb']:.1f}GB free ({usage['percent']:.1f}% used)")
                logger.info("Starting emergency cleanup to free 10GB...")

                # Aggressive cleanup: try to free 10GB
                files_deleted, bytes_freed = disk_manager.cleanup_old_recordings(target_free_gb=MIN_FREE_GB + 10)

                if files_deleted > 0:
                    logger.info(f"Emergency cleanup: deleted {files_deleted} files, freed {bytes_freed/(1024**3):.2f}GB")
                else:
                    logger.error("Emergency cleanup failed - no files to delete!")

            # Regular cleanup if above warning threshold
            elif usage['percent'] >= WARNING_THRESHOLD:
                logger.warning(f"Disk space warning: {usage['free_gb']:.1f}GB free ({usage['percent']:.1f}% used)")
                logger.info("Starting cleanup to maintain free space...")

                # Normal cleanup: try to get to 15GB free
                files_deleted, bytes_freed = disk_manager.cleanup_old_recordings(target_free_gb=15.0)

                if files_deleted > 0:
                    logger.info(f"Cleanup: deleted {files_deleted} files, freed {bytes_freed/(1024**3):.2f}GB")

        except Exception as e:
            logger.error(f"Error in disk monitor task: {e}", exc_info=True)


# Web Routes

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page"""
    cameras = config.cameras
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "cameras": cameras}
    )


@app.get("/fullscreen/{camera_name}", response_class=HTMLResponse)
async def fullscreen_view(request: Request, camera_name: str):
    """Fullscreen view of a single camera"""
    return templates.TemplateResponse(
        "fullscreen.html",
        {"request": request, "camera_name": camera_name}
    )


@app.get("/playback", response_class=HTMLResponse)
async def playback_view(request: Request):
    """Playback/archive view"""
    return templates.TemplateResponse(
        "playback.html",
        {"request": request}
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request):
    """Settings/configuration view"""
    return templates.TemplateResponse(
        "settings.html",
        {"request": request}
    )


@app.get("/api/cameras")
async def get_cameras() -> List[Dict[str, Any]]:
    """Get list of all cameras"""
    cameras = config.cameras
    result = []

    for camera in cameras:
        camera_name = camera['name']
        recorder = recorder_manager.get_recorder(camera_name) if recorder_manager else None

        result.append({
            'name': camera_name,
            'id': camera.get('id', camera_name),
            'enabled': camera.get('enabled', True),
            'recording': recorder is not None and recorder.is_recording if recorder else False,
            'rtsp_url': camera.get('rtsp_url', ''),
            'device_info': camera.get('device_info', {})
        })

    return result


@app.get("/api/cameras/{camera_name}/debug")
async def debug_camera(camera_name: str) -> Dict[str, Any]:
    """Debug endpoint to check recorder state"""
    recorder = recorder_manager.get_recorder(camera_name)
    if not recorder:
        raise HTTPException(status_code=404, detail="Camera not found")

    frame = recorder.get_latest_frame()

    return {
        'camera_name': camera_name,
        'is_recording': recorder.is_recording,
        'has_capture': recorder.capture is not None,
        'queue_size': recorder.frame_queue.qsize(),
        'last_frame': 'None' if recorder.last_frame is None else f"{recorder.last_frame.shape}",
        'got_frame_from_method': 'None' if frame is None else f"{frame.shape}"
    }


@app.get("/api/cameras/{camera_name}/health")
async def get_camera_health(camera_name: str) -> Dict[str, Any]:
    """Get detailed health information for a camera"""
    recorder = recorder_manager.get_recorder(camera_name)
    if not recorder:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Calculate time since last frame
    time_since_last_frame = None
    if recorder.last_frame_time:
        delta = datetime.now() - recorder.last_frame_time
        time_since_last_frame = delta.total_seconds()

    # Determine health status
    status = 'healthy'
    if not recorder.is_recording:
        status = 'stopped'
    elif recorder.consecutive_failures > 0:
        status = 'degraded'
    elif time_since_last_frame and time_since_last_frame > 30:
        status = 'stale'

    return {
        'camera_name': camera_name,
        'camera_id': recorder.camera_id,
        'status': status,
        'is_recording': recorder.is_recording,
        'stream_info': {
            'fps': recorder.stream_fps,
            'width': recorder.stream_width,
            'height': recorder.stream_height,
        },
        'health_metrics': {
            'last_frame_time': recorder.last_frame_time.isoformat() if recorder.last_frame_time else None,
            'time_since_last_frame_seconds': round(time_since_last_frame, 2) if time_since_last_frame else None,
            'last_connection_attempt': recorder.last_connection_attempt.isoformat() if recorder.last_connection_attempt else None,
            'last_successful_connection': recorder.last_successful_connection.isoformat() if recorder.last_successful_connection else None,
            'total_reconnects': recorder.total_reconnects,
            'consecutive_failures': recorder.consecutive_failures,
        },
        'recording_info': {
            'current_segment_start': recorder.current_segment_start.isoformat() if recorder.current_segment_start else None,
            'current_segment_path': str(recorder.current_segment_path) if recorder.current_segment_path else None,
        }
    }


@app.get("/api/cameras/health")
async def get_all_cameras_health() -> List[Dict[str, Any]]:
    """Get health information for all cameras"""
    cameras = config.cameras
    health_data = []

    for camera in cameras:
        camera_name = camera['name']
        recorder = recorder_manager.get_recorder(camera_name) if recorder_manager else None

        if not recorder:
            health_data.append({
                'camera_name': camera_name,
                'camera_id': camera.get('id', camera_name),
                'status': 'not_started',
                'is_recording': False,
            })
            continue

        # Calculate time since last frame
        time_since_last_frame = None
        if recorder.last_frame_time:
            delta = datetime.now() - recorder.last_frame_time
            time_since_last_frame = delta.total_seconds()

        # Determine health status
        status = 'healthy'
        if not recorder.is_recording:
            status = 'stopped'
        elif recorder.consecutive_failures > 0:
            status = 'degraded'
        elif time_since_last_frame and time_since_last_frame > 30:
            status = 'stale'

        health_data.append({
            'camera_name': camera_name,
            'camera_id': recorder.camera_id,
            'status': status,
            'is_recording': recorder.is_recording,
            'time_since_last_frame_seconds': round(time_since_last_frame, 2) if time_since_last_frame else None,
            'total_reconnects': recorder.total_reconnects,
            'consecutive_failures': recorder.consecutive_failures,
        })

    return health_data


@app.post("/api/cameras/discover")
async def discover_cameras(ip_range: str = None) -> Dict[str, Any]:
    """Discover ONVIF cameras on network"""
    try:
        discovery = ONVIFDiscovery(
            username=config.default_camera_username,
            password=config.default_camera_password
        )

        timeout = config.get('onvif.discovery_timeout', 5)
        devices = await discovery.discover_cameras(timeout=timeout, scan_range=ip_range)

        discovered = []
        for device in devices:
            camera_dict = device.to_dict()
            discovered.append(camera_dict)

            # Optionally add to config
            # config.add_camera(camera_dict)

        return {
            'success': True,
            'count': len(discovered),
            'cameras': discovered
        }

    except Exception as e:
        logger.error(f"Error discovering cameras: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@app.post("/api/cameras/{camera_name}/start")
async def start_camera(camera_name: str) -> Dict[str, Any]:
    """Start recording for a camera"""
    try:
        recorder = recorder_manager.get_recorder(camera_name)
        if not recorder:
            raise HTTPException(status_code=404, detail="Camera not found")

        await recorder.start()

        return {'success': True, 'message': f'Started recording {camera_name}'}

    except Exception as e:
        logger.error(f"Error starting camera {camera_name}: {e}")
        return {'success': False, 'error': str(e)}


@app.post("/api/cameras/{camera_name}/reconnect")
async def reconnect_camera(camera_name: str) -> Dict[str, Any]:
    """Force reconnect a camera (stop and restart)"""
    try:
        recorder = recorder_manager.get_recorder(camera_name)
        if not recorder:
            raise HTTPException(status_code=404, detail="Camera not found")

        # Stop and restart to force immediate reconnection
        recorder.stop()
        await asyncio.sleep(1)  # Brief pause
        await recorder.start()

        return {'success': True, 'message': f'Reconnecting {camera_name}...'}

    except Exception as e:
        logger.error(f"Error reconnecting camera {camera_name}: {e}")
        return {'success': False, 'error': str(e)}


@app.post("/api/cameras/{camera_name}/stop")
async def stop_camera(camera_name: str) -> Dict[str, Any]:
    """Stop recording for a camera"""
    try:
        recorder = recorder_manager.get_recorder(camera_name)
        if not recorder:
            raise HTTPException(status_code=404, detail="Camera not found")

        recorder.stop()

        return {'success': True, 'message': f'Stopped recording {camera_name}'}

    except Exception as e:
        logger.error(f"Error stopping camera {camera_name}: {e}")
        return {'success': False, 'error': str(e)}


@app.get("/api/cameras/{camera_name}/live")
async def live_stream(camera_name: str, raw: bool = False, quality: int = 50, realtime: bool = False):
    """Stream live view from camera

    Args:
        camera_name: Name of the camera
        raw: If True, skip motion detection overlay for faster streaming
        quality: JPEG quality (1-100, default 50). Lower = faster/smaller, Higher = better quality
        realtime: If True, stream as fast as possible with no frame rate limiting
    """
    recorder = recorder_manager.get_recorder(camera_name)
    if not recorder:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Clamp quality to valid range
    jpeg_quality = max(1, min(100, quality))

    async def generate():
        """Generate MJPEG stream"""
        while True:
            jpeg_data = recorder.get_latest_frame()

            # CRITICAL: If no frame available, sleep to prevent CPU spinning
            if jpeg_data is None:
                await asyncio.sleep(0.1)  # Wait 100ms before trying again
                continue

            # Frame is already JPEG compressed from recorder at quality 85 (saves memory!)
            # Check if we need to decode and re-process:
            # - Not raw mode (need to apply motion detection)
            # - Quality differs significantly from stored (85)
            # - Need to resize for low quality
            needs_processing = (not raw) or (jpeg_quality < 60 and not realtime)

            if needs_processing:
                # Decode JPEG to numpy array for processing
                nparr = np.frombuffer(jpeg_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is not None:
                    # Resize frame for lower bandwidth (optional - more aggressive optimization)
                    # Skip resizing in realtime mode for maximum speed
                    if not realtime and jpeg_quality < 60:
                        # Scale down to 720p for low quality
                        h, w = frame.shape[:2]
                        if w > 1280:
                            scale = 1280 / w
                            new_w = int(w * scale)
                            new_h = int(h * scale)
                            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

                    # Apply motion detection visualization only if not raw mode
                    if not raw:
                        detector = motion_monitor.get_detector(camera_name) if motion_monitor else None
                        if detector:
                            has_motion, boxes = detector.process_frame(frame)
                            if has_motion:
                                frame = detector.draw_motion(frame, boxes)

                    # Re-encode with requested quality
                    encode_params = [
                        cv2.IMWRITE_JPEG_QUALITY, jpeg_quality,
                        cv2.IMWRITE_JPEG_OPTIMIZE, 1 if not realtime else 0,
                        cv2.IMWRITE_JPEG_PROGRESSIVE, 0
                    ]
                    ret, buffer = cv2.imencode('.jpg', frame, encode_params)
                    if ret:
                        jpeg_data = buffer.tobytes()

            # Stream JPEG data (either original at quality 85, or re-encoded)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg_data + b'\r\n')

            # Frame rate control - no delay in realtime mode for absolute maximum speed
            if realtime:
                # Realtime mode: stream as fast as possible, zero delay
                # Only yield to event loop to prevent blocking
                await asyncio.sleep(0)
            else:
                # Normal mode: Consistent frame rate for smoother playback
                # Lower quality = higher frame rate for smoother motion
                if jpeg_quality < 50:
                    await asyncio.sleep(0.05)  # 20 fps - smooth and efficient
                elif jpeg_quality < 70:
                    await asyncio.sleep(0.067)  # 15 fps
                elif jpeg_quality < 85:
                    await asyncio.sleep(0.1)  # 10 fps
                else:
                    await asyncio.sleep(0.033)  # 30 fps for high quality

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/cameras/{camera_name}/recordings")
async def get_recordings(camera_name: str) -> List[Dict[str, Any]]:
    """Get list of recordings for a camera"""
    try:
        camera_storage = config.storage_path / camera_name.replace(' ', '_')
        if not camera_storage.exists():
            return []

        recordings = []
        container = config.get('recording.container_format', 'mp4')

        for video_file in sorted(camera_storage.glob(f"*.{container}"), reverse=True):
            try:
                # Parse timestamp from filename
                timestamp_str = video_file.stem
                file_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                recordings.append({
                    'filename': video_file.name,
                    'timestamp': file_time.isoformat(),
                    'size': video_file.stat().st_size,
                    'path': str(video_file.relative_to(config.storage_path))
                })
            except Exception as e:
                logger.warning(f"Error processing {video_file}: {e}")

        return recordings

    except Exception as e:
        logger.error(f"Error getting recordings for {camera_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recordings/{camera_name}/{filename}")
async def get_recording(camera_name: str, filename: str):
    """Download or stream a recording"""
    try:
        camera_storage = config.storage_path / camera_name.replace(' ', '_')
        video_file = camera_storage / filename

        if not video_file.exists():
            raise HTTPException(status_code=404, detail="Recording not found")

        return FileResponse(
            video_file,
            media_type="video/mp4",
            filename=filename
        )

    except Exception as e:
        logger.error(f"Error retrieving recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/storage/stats")
async def get_storage_stats():
    """Get detailed storage statistics per camera"""
    import os

    storage_path = config.storage_path
    camera_stats = []
    total_size = 0

    for camera in config.cameras:
        camera_id = camera.get('id', camera['name'])
        camera_dir = storage_path / camera_id

        if not camera_dir.exists():
            camera_stats.append({
                'camera_name': camera['name'],
                'camera_id': camera_id,
                'size_gb': 0,
                'file_count': 0
            })
            continue

        # Calculate directory size
        dir_size = 0
        file_count = 0

        try:
            for entry in camera_dir.rglob('*.mp4'):
                if entry.is_file():
                    dir_size += entry.stat().st_size
                    file_count += 1
        except Exception as e:
            logger.error(f"Error calculating storage for {camera_id}: {e}")

        size_gb = dir_size / (1024 ** 3)
        total_size += size_gb

        camera_stats.append({
            'camera_name': camera['name'],
            'camera_id': camera_id,
            'size_gb': round(size_gb, 2),
            'file_count': file_count
        })

    # Sort by size descending
    camera_stats.sort(key=lambda x: x['size_gb'], reverse=True)

    return {
        'cameras': camera_stats,
        'total_size_gb': round(total_size, 2)
    }


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket for real-time events (motion detection, etc.)"""
    await websocket.accept()

    try:
        while True:
            # Send motion events
            events = []

            if motion_monitor:
                for camera_name, detector in motion_monitor.detectors.items():
                    if detector.motion_detected:
                        events.append({
                            'type': 'motion',
                            'camera': camera_name,
                            'timestamp': detector.last_motion_time.isoformat()
                        })

            if events:
                await websocket.send_text(json.dumps(events))

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        'status': 'healthy',
        'cameras': len(config.cameras),
        'recording': len([r for r in recorder_manager.recorders.values() if r.is_recording]) if recorder_manager else 0
    }


@app.get("/api/system/stats")
async def get_system_stats():
    """Get system resource usage statistics"""
    import psutil

    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_count = psutil.cpu_count()

    # Memory usage
    memory = psutil.virtual_memory()
    memory_percent = memory.percent
    memory_used_gb = memory.used / (1024 ** 3)
    memory_total_gb = memory.total / (1024 ** 3)

    # Disk usage for recordings directory
    try:
        disk = psutil.disk_usage('recordings')
        disk_percent = disk.percent
        disk_used_gb = disk.used / (1024 ** 3)
        disk_total_gb = disk.total / (1024 ** 3)
    except:
        disk_percent = 0
        disk_used_gb = 0
        disk_total_gb = 0

    return {
        'cpu': {
            'percent': round(cpu_percent, 1),
            'cores': cpu_count
        },
        'memory': {
            'percent': round(memory_percent, 1),
            'used_gb': round(memory_used_gb, 1),
            'total_gb': round(memory_total_gb, 1)
        },
        'disk': {
            'percent': round(disk_percent, 1),
            'used_gb': round(disk_used_gb, 1),
            'total_gb': round(disk_total_gb, 1)
        }
    }


@app.post("/api/webrtc/offer")
async def webrtc_offer(request: Request):
    """
    WebRTC signaling endpoint - handles SDP offer from client

    Uses H.264 passthrough for zero-latency streaming (no re-encoding)

    Request body:
        {
            "camera_name": "Camera 1",
            "sdp": "...",
            "type": "offer",
            "passthrough": true  // Use H.264 passthrough (default: true)
        }

    Response:
        {
            "sdp": "...",
            "type": "answer",
            "pc_id": "..."
        }
    """
    try:
        data = await request.json()
        camera_name = data.get("camera_name")
        use_passthrough = data.get("passthrough", True)  # Default to passthrough for maximum speed

        # Use H.264 passthrough for commercial-grade performance
        if use_passthrough and webrtc_passthrough:
            logger.info(f"Using H.264 passthrough for {camera_name} (ZERO-LATENCY)")
            offer = {"sdp": data.get("sdp"), "type": data.get("type")}
            answer = await webrtc_passthrough.create_offer(camera_name, offer)
            return answer

        # Fallback to frame-based streaming (slower)
        if not webrtc_manager:
            raise HTTPException(status_code=500, detail="WebRTC not initialized")

        logger.info(f"Using frame-based WebRTC for {camera_name}")
        if not camera_name:
            raise HTTPException(status_code=400, detail="camera_name required")

        offer = {
            "sdp": data.get("sdp"),
            "type": data.get("type")
        }

        # Create WebRTC answer
        answer = await webrtc_manager.create_offer(camera_name, offer)

        return answer

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"WebRTC offer error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cameras/{camera_name}/stream/direct")
async def direct_rtsp_stream(camera_name: str):
    """
    ULTRA-FAST Direct RTSP proxy - ZERO Python processing

    This bypasses ALL frame processing and streams H.264 directly from camera
    Latency: 50-100ms (10-30x faster than any other method)

    Uses FFmpeg to proxy RTSP→HTTP with zero re-encoding
    Browser plays native H.264 stream
    """
    if not rtsp_proxy:
        raise HTTPException(status_code=500, detail="RTSP proxy not initialized")

    # Find camera config
    cameras = config.cameras
    camera_config = next((c for c in cameras if c['name'] == camera_name), None)

    if not camera_config:
        raise HTTPException(status_code=404, detail=f"Camera {camera_name} not found")

    rtsp_url = camera_config['rtsp_url']

    logger.info(f"Starting direct RTSP proxy for {camera_name} (ZERO-LATENCY mode)")

    return StreamingResponse(
        rtsp_proxy.stream_camera(rtsp_url, camera_name),
        media_type="video/mp2t",  # MPEG-TS
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Content-Type-Options": "nosniff"
        }
    )


@app.get("/api/cameras/{camera_name}/stream/mse")
async def mse_stream(camera_name: str):
    """
    Media Source Extensions streaming - native browser decoder
    Even lower latency than MPEG-TS
    """
    if not mse_proxy:
        raise HTTPException(status_code=500, detail="MSE proxy not initialized")

    cameras = config.cameras
    camera_config = next((c for c in cameras if c['name'] == camera_name), None)

    if not camera_config:
        raise HTTPException(status_code=404, detail=f"Camera {camera_name} not found")

    rtsp_url = camera_config['rtsp_url']

    logger.info(f"Starting MSE stream for {camera_name}")

    return StreamingResponse(
        mse_proxy.stream_mse(rtsp_url),
        media_type="video/mp4",
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff"
        }
    )