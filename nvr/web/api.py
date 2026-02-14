"""FastAPI web application for NVR"""

import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Response
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

# CORS middleware for mobile app / cross-origin access
from starlette.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates and static files
templates = Jinja2Templates(directory="nvr/templates")
app.mount("/static", StaticFiles(directory="nvr/static"), name="static")

# Include extensions
from nvr.web.api_extensions import router as extensions_router
from nvr.web.playback_api import router as playback_router
from nvr.web.settings_api import router as settings_router
from nvr.web.recording_api import router as recording_router
app.include_router(extensions_router)
app.include_router(playback_router)
app.include_router(settings_router)
app.include_router(recording_router)

# Global instances
recorder_manager: RecorderManager = None
motion_monitor: MotionMonitor = None
ai_monitor: AIDetectionMonitor = None
playback_db: PlaybackDatabase = None
storage_manager = None
alert_system = None
recording_mode_manager = None
webrtc_manager: WebRTCManager = None
webrtc_passthrough: WebRTCPassthroughManager = None
rtsp_proxy: RTSPProxy = None
mse_proxy: MSEStreamProxy = None
sd_card_manager = None


@app.on_event("startup")
async def startup_event():
    """Initialize NVR on startup"""
    global recorder_manager, motion_monitor, ai_monitor, playback_db, storage_manager, recording_mode_manager, webrtc_manager, webrtc_passthrough, rtsp_proxy, mse_proxy, sd_card_manager

    logger.info("Starting NVR...")

    # Start background cache cleaner for transcoded files
    from nvr.core.cache_cleaner import get_cache_cleaner
    get_cache_cleaner()  # Starts automatically

    # Queue existing mp4v files for background transcoding (non-blocking)
    from nvr.core.transcoder import get_transcoder
    import subprocess
    import threading
    transcoder = get_transcoder()

    def queue_mp4v_files_async():
        """Background task to find and queue mp4v files for transcoding"""
        queued_count = 0
        for video_file in config.storage_path.rglob("*.mp4"):
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

    # Start the mp4v scan in background so it doesn't block server startup
    threading.Thread(target=queue_mp4v_files_async, daemon=True, name="Mp4vScanner").start()
    logger.info("Started background scan for mp4v files to transcode")

    # Optimize OpenCV for multi-threading
    import os
    num_threads = os.cpu_count() or 4
    cv2.setNumThreads(num_threads)
    logger.info(f"OpenCV configured to use {num_threads} threads")

    # Initialize playback database
    db_path = config.storage_path / "playback.db"
    playback_db = PlaybackDatabase(db_path)
    logger.info(f"Playback database initialized at {db_path}")

    # Initialize SD card recordings manager for fallback access
    from nvr.core.sd_card_manager import SDCardRecordingsManager
    sd_card_config = config.get('sd_card_fallback', {})
    sd_card_manager = SDCardRecordingsManager(
        playback_db=playback_db,
        cache_duration=sd_card_config.get('cache_duration_seconds', 300),
        query_timeout=30.0
    )
    if sd_card_config.get('enabled', True):
        logger.info("SD card fallback manager initialized")
    else:
        logger.info("SD card fallback is disabled in config")

    # Schedule periodic database maintenance (runs every 24 hours)
    from nvr.core.db_maintenance import schedule_maintenance
    schedule_maintenance(playback_db, interval_hours=24)
    logger.info("Database maintenance scheduled")

    # Initialize storage manager for automatic cleanup
    from nvr.core.storage_manager import StorageManager
    storage_manager = StorageManager(
        storage_path=config.storage_path,
        playback_db=playback_db,
        retention_days=config.get('storage.retention_days', config.get('recording.retention_days', 7)),
        cleanup_threshold_percent=config.get('storage.cleanup_threshold_percent', 85.0),
        target_percent=config.get('storage.target_percent', 75.0),
        reserved_space_gb=config.get('storage.reserved_space_gb', 0.0)
    )
    logger.info(f"Storage manager initialized: {storage_manager.retention_days} day retention, cleanup at {storage_manager.cleanup_threshold}%")

    # Schedule periodic storage cleanup checks (every 6 hours)
    def schedule_storage_cleanup():
        import threading
        import time

        def cleanup_loop():
            while True:
                try:
                    time.sleep(6 * 3600)  # 6 hours
                    logger.info("Running scheduled storage cleanup check")
                    stats = storage_manager.check_and_cleanup()
                    if stats['cleanup_triggered']:
                        logger.info(f"Storage cleanup completed: deleted {stats['files_deleted']} files, freed {stats['space_freed_gb']:.2f} GB")
                except Exception as e:
                    logger.error(f"Error in storage cleanup loop: {e}")

        thread = threading.Thread(target=cleanup_loop, daemon=True, name="StorageCleanup")
        thread.start()
        return thread

    schedule_storage_cleanup()
    logger.info("Storage cleanup scheduler started (checks every 6 hours)")

    # Initialize alert system
    from nvr.core.alert_system import alert_system as alert_sys
    alert_system = alert_sys

    # Add webhook handler if configured
    webhook_url = config.get('alerts.webhook_url')
    if webhook_url:
        from nvr.core.alert_system import WebhookAlertHandler
        alert_system.add_handler(WebhookAlertHandler(webhook_url))
        logger.info(f"Alert webhook configured: {webhook_url}")

    # Schedule periodic health checks (every 2 minutes)
    def schedule_health_monitoring():
        import threading
        import time

        async def health_check_loop():
            while True:
                try:
                    await asyncio.sleep(120)  # 2 minutes

                    # Check all cameras
                    response = await get_all_cameras_health()
                    for camera_health in response:
                        await alert_system.check_camera_health(
                            camera_health['camera_name'],
                            camera_health
                        )

                    # Check storage
                    import psutil
                    disk = psutil.disk_usage(str(config.storage_path))
                    await alert_system.check_storage(
                        disk.percent,
                        disk.free / (1024**3)
                    )

                except Exception as e:
                    logger.error(f"Error in health monitoring loop: {e}")

        def run_async_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(health_check_loop())

        thread = threading.Thread(target=run_async_loop, daemon=True, name="HealthMonitor")
        thread.start()
        return thread

    schedule_health_monitoring()
    logger.info("Health monitoring scheduler started (checks every 2 minutes)")

    # Initialize recording mode manager
    from nvr.core.recording_modes import RecordingModeManager, RecordingMode, create_business_hours, create_night_hours
    recording_mode_manager = RecordingModeManager()

    # Configure default recording mode from config
    default_mode_str = config.get('recording.default_mode', 'continuous')
    try:
        default_mode = RecordingMode(default_mode_str)
        recording_mode_manager.default_config.mode = default_mode
        logger.info(f"Default recording mode: {default_mode.value}")
    except ValueError:
        logger.warning(f"Invalid default recording mode '{default_mode_str}', using continuous")

    # Configure per-camera modes from config (legacy format)
    camera_modes = config.get('recording.camera_modes', {})
    if camera_modes:
        for camera_name, mode_str in camera_modes.items():
            try:
                mode = RecordingMode(mode_str)
                recording_mode_manager.set_camera_mode(camera_name, mode)
                logger.info(f"Recording mode for {camera_name}: {mode.value}")
            except ValueError:
                logger.warning(f"Invalid recording mode '{mode_str}' for {camera_name}")

    # Configure per-camera modes from camera settings (new format)
    cameras = config.get('cameras', [])
    for cam in cameras:
        cam_name = cam.get('name')
        mode_str = cam.get('recording_mode')
        if cam_name and mode_str:
            try:
                mode = RecordingMode(mode_str)
                recording_mode_manager.set_camera_mode(cam_name, mode)
                logger.info(f"Recording mode for {cam_name}: {mode.value} (resolution: {cam.get('resolution', 'default')}p)")
            except ValueError:
                logger.warning(f"Invalid recording mode '{mode_str}' for {cam_name}")

    # Initialize recorder manager with database and recording mode manager
    recorder_manager = RecorderManager(
        storage_path=config.storage_path,
        segment_duration=config.get('recording.segment_duration', 300),
        playback_db=playback_db,
        recording_mode_manager=recording_mode_manager
    )

    # Motion detection method: 'frame_diff', 'ai_only', or 'both'
    motion_method = config.get('motion_detection.method', 'frame_diff')
    use_frame_diff = motion_method in ('frame_diff', 'both')
    use_ai = motion_method in ('ai_only', 'both') or config.get('ai_detection.enabled', False)

    # Initialize motion monitor (frame-difference detection)
    motion_monitor = MotionMonitor() if use_frame_diff else None
    if use_frame_diff:
        logger.info("Frame-difference motion detection enabled")

    # Initialize AI detection monitor
    if use_ai:
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

    # Load all cameras - disabled cameras get live view but no recording
    cameras = config.cameras
    recording_enabled = config.get('recording.enabled', True)
    recording_count = 0

    for camera in cameras:
        camera_name = camera['name']
        camera_id = camera.get('id', camera_name)  # Fallback to name if no ID
        rtsp_url = camera['rtsp_url']
        camera_enabled = camera.get('enabled', True)

        # Add camera to recorder manager
        # All cameras connect for live view, but disabled cameras don't record
        should_record = recording_enabled and camera_enabled
        streaming_only = not should_record

        await recorder_manager.add_camera(
            camera_name, rtsp_url,
            camera_id=camera_id,
            auto_start=True,  # Always start for live view
            streaming_only=streaming_only
        )

        if should_record:
            recording_count += 1
            # Add motion detector if enabled (frame-difference method)
            if config.get('motion_detection.enabled', True) and motion_monitor:
                recorder = recorder_manager.get_recorder(camera_name)
                motion_monitor.add_camera(
                    camera_name,
                    sensitivity=config.get('motion_detection.sensitivity', 25),
                    min_area=config.get('motion_detection.min_area', 500),
                    recorder=recorder
                )

            # Add AI detector if enabled
            if use_ai and ai_monitor:
                recorder = recorder_manager.get_recorder(camera_name)
                ai_monitor.add_camera(
                    camera_name,
                    recorder=recorder,
                    confidence_threshold=config.get('ai_detection.confidence_threshold', 0.5)
                )
        else:
            logger.info(f"Camera {camera_name} loaded (streaming only, recording disabled)")

    logger.info(f"Started recording on {recording_count}/{len(cameras)} camera(s)")

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

    # Start motion monitoring (frame-difference)
    if config.get('motion_detection.enabled', True) and motion_monitor and motion_monitor.detectors:
        asyncio.create_task(motion_monitor.start_monitoring(recorder_manager))
        logger.info(f"Motion monitoring started for {len(motion_monitor.detectors)} cameras (method: {motion_method})")
    elif not motion_monitor:
        logger.info("Frame-difference motion detection disabled (using AI-only mode)")
    else:
        logger.warning(f"Motion monitoring NOT started - enabled: {config.get('motion_detection.enabled', True)}")

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


@app.get("/fullscreen/{camera_id}", response_class=HTMLResponse)
async def fullscreen_view(request: Request, camera_id: str):
    """Fullscreen view of a single camera"""
    # Look up camera name for display
    camera_name = camera_id
    for camera in config.cameras:
        if camera.get('id') == camera_id or camera['name'] == camera_id:
            camera_name = camera['name']
            break
    return templates.TemplateResponse(
        "fullscreen.html",
        {"request": request, "camera_id": camera_id, "camera_name": camera_name}
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
async def get_cameras(response: Response) -> List[Dict[str, Any]]:
    """Get list of all cameras"""
    # Prevent caching to ensure fresh data after renames
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"

    cameras = config.cameras
    result = []

    for camera in cameras:
        camera_name = camera['name']
        recorder = recorder_manager.get_recorder(camera_name) if recorder_manager else None

        # Recording means connected AND writing to disk (not streaming_only)
        is_recording = (recorder is not None and
                       recorder.is_recording and
                       not recorder.streaming_only) if recorder else False

        result.append({
            'name': camera_name,
            'id': camera.get('id', camera_name),
            'enabled': camera.get('enabled', True),
            'recording': is_recording,
            'streaming': recorder is not None and recorder.is_recording if recorder else False,
            'rtsp_url': camera.get('rtsp_url', ''),
            'device_info': camera.get('device_info', {})
        })

    return result


@app.get("/api/cameras/{camera_id}/debug")
async def debug_camera(camera_id: str) -> Dict[str, Any]:
    """Debug endpoint to check recorder state"""
    try:
        recorder = recorder_manager.get_recorder_by_id(camera_id)
        if not recorder:
            raise HTTPException(status_code=404, detail="Camera not found")

        frame = recorder.get_latest_frame()

        return {
            'camera_id': camera_id,
            'camera_name': recorder.camera_name,
            'is_recording': recorder.is_recording,
            'streaming_only': recorder.streaming_only,
            'has_capture': recorder.capture is not None,
            'capture_opened': recorder.capture.isOpened() if recorder.capture else False,
            'queue_size': recorder.frame_queue.qsize() if recorder.frame_queue else 0,
            'last_frame_bytes': 'None' if recorder.last_frame is None else f"{len(recorder.last_frame)} bytes",
            'got_frame_bytes': 'None' if frame is None else f"{len(frame)} bytes"
        }
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}", exc_info=True)
        return {'error': str(e)}


@app.get("/api/cameras/{camera_id}/health")
async def get_camera_health(camera_id: str) -> Dict[str, Any]:
    """Get detailed health information for a camera"""
    recorder = recorder_manager.get_recorder_by_id(camera_id)
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

        # Get already configured camera IPs to filter them out
        existing_ips = set()
        for cam in config.cameras:
            if cam.get('onvif_host'):
                existing_ips.add(cam['onvif_host'])
            # Also extract IP from RTSP URL
            rtsp = cam.get('rtsp_url', '')
            if '@' in rtsp and ':' in rtsp:
                try:
                    ip_part = rtsp.split('@')[1].split(':')[0]
                    existing_ips.add(ip_part)
                except:
                    pass

        discovered = []
        for device in devices:
            camera_dict = device.to_dict()
            # Only include cameras not already configured
            if camera_dict.get('onvif_host') not in existing_ips:
                discovered.append(camera_dict)
            else:
                logger.debug(f"Skipping already-configured camera at {camera_dict.get('onvif_host')}")

        return {
            'success': True,
            'count': len(discovered),
            'cameras': discovered,
            'message': f"Found {len(discovered)} new camera(s)" if discovered else "No new cameras found"
        }

    except Exception as e:
        logger.error(f"Error discovering cameras: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@app.post("/api/cameras/{camera_id}/start")
async def start_camera(camera_id: str, permanent: bool = False) -> Dict[str, Any]:
    """Start recording for a camera

    Args:
        camera_id: ID of the camera to start (also accepts camera name for compatibility)
        permanent: If True, also enable the camera in config (survives restart)
    """
    logger.info(f"start_camera called: camera_id={camera_id}, permanent={permanent}")
    try:
        recorder = recorder_manager.get_recorder_by_id(camera_id)
        logger.info(f"Got recorder: {recorder is not None}")
        if not recorder:
            logger.error(f"Camera not found: {camera_id}")
            logger.info(f"Available cameras: {list(recorder_manager.recorders.keys())}")
            return {'success': False, 'error': f'Camera not found: {camera_id}'}

        camera_name = recorder.camera_name
        logger.info(f"Recorder state: is_recording={recorder.is_recording}, streaming_only={recorder.streaming_only}")

        # If already recording (not streaming_only), nothing to do
        if recorder.is_recording and not recorder.streaming_only:
            logger.info(f"{camera_name} is already recording normally")
            return {'success': True, 'message': f'{camera_name} is already recording', 'permanent': permanent}

        # If in streaming_only mode, we need to restart in recording mode
        if recorder.is_recording and recorder.streaming_only:
            logger.info(f"Stopping streaming_only mode for {camera_name}")
            recorder.stop()
            await asyncio.sleep(0.5)  # Brief pause for cleanup

        # Start recording
        logger.info(f"Starting recorder for {camera_name}")
        await recorder.start(streaming_only=False)
        logger.info(f"Recorder started for {camera_name}")

        message = f'Started recording {camera_name}'

        # If permanent, also enable in config
        if permanent:
            logger.info(f"Enabling {camera_name} in config permanently")
            cameras = config.cameras
            for camera in cameras:
                if camera.get('id') == camera_id or camera['name'] == camera_id:
                    camera['enabled'] = True
                    break
            config.save()
            message += ' (enabled in config)'
            logger.info(f"Camera {camera_name} permanently enabled")

        logger.info(f"Returning success for {camera_name}")
        return {'success': True, 'message': message, 'permanent': permanent}

    except Exception as e:
        logger.error(f"Error starting camera {camera_id}: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


@app.post("/api/cameras/{camera_id}/reconnect")
async def reconnect_camera(camera_id: str) -> Dict[str, Any]:
    """Force reconnect a camera (stop and restart)"""
    try:
        recorder = recorder_manager.get_recorder_by_id(camera_id)
        if not recorder:
            return {'success': False, 'error': f'Camera not found: {camera_id}'}

        camera_name = recorder.camera_name

        # Stop and restart to force immediate reconnection
        recorder.stop()
        await asyncio.sleep(1)  # Brief pause
        await recorder.start()

        return {'success': True, 'message': f'Reconnecting {camera_name}...'}

    except Exception as e:
        logger.error(f"Error reconnecting camera {camera_id}: {e}")
        return {'success': False, 'error': str(e)}


@app.post("/api/cameras/{camera_id}/stop")
async def stop_camera(camera_id: str, permanent: bool = False) -> Dict[str, Any]:
    """Stop recording for a camera (live view continues)

    Args:
        camera_id: ID of the camera to stop (also accepts camera name for compatibility)
        permanent: If True, also disable the camera in config (survives restart)
    """
    logger.info(f"stop_camera called: camera_id={camera_id}, permanent={permanent}")
    try:
        recorder = recorder_manager.get_recorder_by_id(camera_id)
        if not recorder:
            logger.error(f"Camera not found: {camera_id}")
            logger.info(f"Available cameras: {list(recorder_manager.recorders.keys())}")
            return {'success': False, 'error': f'Camera not found: {camera_id}'}

        camera_name = recorder.camera_name
        logger.info(f"Recorder state before stop: is_recording={recorder.is_recording}, streaming_only={recorder.streaming_only}")

        # If already in streaming_only mode, nothing to do
        if recorder.streaming_only:
            logger.info(f"{camera_name} already in streaming_only mode")
            return {'success': True, 'message': f'{camera_name} recording already stopped', 'permanent': permanent}

        # Stop recording and restart in streaming-only mode (keeps live view working)
        logger.info(f"Stopping recorder for {camera_name}")
        recorder.stop()
        await asyncio.sleep(0.5)  # Brief pause for cleanup
        logger.info(f"Starting recorder in streaming_only mode for {camera_name}")
        await recorder.start(streaming_only=True)
        logger.info(f"Recorder state after start: is_recording={recorder.is_recording}, streaming_only={recorder.streaming_only}")

        message = f'Stopped recording {camera_name} (live view continues)'

        # If permanent, also disable in config
        if permanent:
            cameras = config.cameras
            for camera in cameras:
                if camera.get('id') == camera_id or camera['name'] == camera_id:
                    camera['enabled'] = False
                    break
            config.save()
            message += ' (disabled in config)'
            logger.info(f"Camera {camera_name} permanently disabled")

        logger.info(f"stop_camera returning success for {camera_name}")
        return {
            'success': True,
            'message': message,
            'permanent': permanent,
            'is_recording': recorder.is_recording,
            'streaming_only': recorder.streaming_only
        }

    except Exception as e:
        logger.error(f"Error stopping camera {camera_id}: {e}")
        return {'success': False, 'error': str(e)}


@app.get("/api/cameras/{camera_id}/live")
async def live_stream(camera_id: str, raw: bool = False, quality: int = 50, realtime: bool = False):
    """Stream live view from camera

    Args:
        camera_id: ID of the camera (also accepts camera name for compatibility)
        raw: If True, skip motion detection overlay for faster streaming
        quality: JPEG quality (1-100, default 50). Lower = faster/smaller, Higher = better quality
        realtime: If True, stream as fast as possible with no frame rate limiting
    """
    recorder = recorder_manager.get_recorder_by_id(camera_id)
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


@app.get("/api/cameras/{camera_id}/recordings")
async def get_recordings(camera_id: str) -> List[Dict[str, Any]]:
    """Get list of recordings for a camera"""
    try:
        # Find camera name from recorder or config
        recorder = recorder_manager.get_recorder_by_id(camera_id) if recorder_manager else None
        if recorder:
            camera_name = recorder.camera_name
        else:
            # Fallback: search config for camera
            camera_name = camera_id
            for cam in config.cameras:
                if cam.get('id') == camera_id or cam['name'] == camera_id:
                    camera_name = cam['name']
                    break

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
        logger.error(f"Error getting recordings for {camera_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recordings/{camera_id}/{filename}")
async def get_recording(camera_id: str, filename: str):
    """Download or stream a recording"""
    try:
        camera_storage = config.storage_path / camera_id.replace(' ', '_')
        video_file = camera_storage / filename

        # Prevent path traversal
        resolved_file = video_file.resolve()
        resolved_storage = config.storage_path.resolve()
        if not str(resolved_file).startswith(str(resolved_storage)):
            raise HTTPException(status_code=403, detail="Access denied")

        if not resolved_file.exists():
            raise HTTPException(status_code=404, detail="Recording not found")

        return FileResponse(
            resolved_file,
            media_type="video/mp4",
            filename=resolved_file.name
        )

    except HTTPException:
        raise
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


@app.websocket("/ws/camera/{camera_id}/stream")
async def websocket_camera_stream(websocket: WebSocket, camera_id: str):
    """WebSocket for camera video stream - bypasses browser HTTP connection limits"""
    await websocket.accept()

    # Find camera
    camera = None
    for cam in config.cameras:
        if cam.get('id') == camera_id or cam.get('name') == camera_id:
            camera = cam
            break

    if not camera:
        await websocket.close(code=4004, reason="Camera not found")
        return

    camera_name = camera.get('name', camera_id)
    logger.info(f"WebSocket stream started for {camera_name}")

    try:
        import base64

        # Get recorder for this camera (try by ID first, then by name)
        recorder = recorder_manager.get_recorder_by_id(camera_id) if recorder_manager else None
        if not recorder:
            recorder = recorder_manager.get_recorder(camera_name) if recorder_manager else None

        if not recorder:
            logger.warning(f"WebSocket: No recorder found for {camera_id} / {camera_name}")
            await websocket.close(code=4004, reason="Camera not recording")
            return

        frame_interval = 1.0 / 10  # 10 FPS target (reduced from 15 for better frame quality)
        last_frame_time = 0
        last_frame_size = 0  # Track frame size for corruption detection
        frames_sent = 0
        no_frame_count = 0

        while True:
            current_time = asyncio.get_event_loop().time()

            # Rate limit
            if current_time - last_frame_time < frame_interval:
                await asyncio.sleep(0.01)
                continue

            # Get latest frame from recorder (already JPEG encoded)
            jpeg_data = recorder.get_latest_frame()

            if jpeg_data is not None:
                # Validate JPEG data before sending
                # Valid JPEG must:
                # 1. Start with FFD8 (SOI marker)
                # 2. End with FFD9 (EOI marker)
                # 3. Be at least 20KB (washed out/corrupted frames are often smaller)
                # 4. Not be drastically smaller than last good frame (sudden quality drop = corruption)
                MIN_FRAME_SIZE = 20000  # 20KB minimum (increased from 5KB)
                frame_size = len(jpeg_data)
                is_valid_jpeg = (
                    frame_size >= MIN_FRAME_SIZE and
                    jpeg_data[0:2] == b'\xff\xd8' and  # Start of Image
                    jpeg_data[-2:] == b'\xff\xd9'      # End of Image
                )

                # Also check for sudden size drops (likely corruption)
                # If frame is less than 50% of last good frame size, reject it
                if is_valid_jpeg and last_frame_size > 0:
                    if frame_size < last_frame_size * 0.5:
                        is_valid_jpeg = False

                if is_valid_jpeg:
                    # Send as base64 (frame is already JPEG bytes)
                    frame_data = base64.b64encode(jpeg_data).decode('utf-8')
                    await websocket.send_text(frame_data)
                    last_frame_time = current_time
                    last_frame_size = frame_size  # Update reference size
                    frames_sent += 1
                    if frames_sent == 1:
                        logger.info(f"WebSocket first frame sent for {camera_name} ({frame_size} bytes)")
                    no_frame_count = 0
                else:
                    # Skip corrupted frame
                    if frames_sent > 0 and frames_sent % 100 == 0:
                        logger.warning(f"WebSocket skipping corrupted frame for {camera_name} (size: {frame_size}, last_good: {last_frame_size})")
            else:
                no_frame_count += 1
                if no_frame_count == 50:  # Log after ~5 seconds of no frames
                    logger.warning(f"WebSocket no frames available for {camera_name}")
                    no_frame_count = 0
                await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.info(f"WebSocket stream disconnected for {camera_name}")
    except Exception as e:
        logger.error(f"WebSocket stream error for {camera_name}: {e}")


@app.get("/api/storage/cleanup/status")
async def get_cleanup_status():
    """Get current storage cleanup status and statistics"""
    if not storage_manager:
        raise HTTPException(status_code=503, detail="Storage manager not initialized")

    try:
        # Get disk usage
        import psutil
        disk = psutil.disk_usage(str(config.storage_path))

        # Get retention stats
        retention_stats = storage_manager.get_retention_stats()

        return {
            'disk_usage': {
                'percent': round(disk.percent, 1),
                'used_gb': round(disk.used / (1024**3), 1),
                'free_gb': round(disk.free / (1024**3), 1),
                'total_gb': round(disk.total / (1024**3), 1)
            },
            'cleanup_config': {
                'retention_days': storage_manager.retention_days,
                'cleanup_threshold_percent': storage_manager.cleanup_threshold,
                'target_percent': storage_manager.target_percent,
                'reserved_space_gb': storage_manager.reserved_space_gb
            },
            'retention_stats': retention_stats
        }
    except Exception as e:
        logger.error(f"Error getting cleanup status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/storage/cleanup/run")
async def run_manual_cleanup():
    """Manually trigger storage cleanup"""
    if not storage_manager:
        raise HTTPException(status_code=503, detail="Storage manager not initialized")

    try:
        logger.info("Manual storage cleanup triggered via API")
        stats = storage_manager.check_and_cleanup()

        return {
            'success': True,
            'cleanup_triggered': stats['cleanup_triggered'],
            'initial_usage_percent': stats['initial_usage_percent'],
            'final_usage_percent': stats['final_usage_percent'],
            'files_deleted': stats['files_deleted'],
            'space_freed_gb': round(stats['space_freed_gb'], 2),
            'message': f"Deleted {stats['files_deleted']} files, freed {stats['space_freed_gb']:.2f} GB" if stats['cleanup_triggered'] else "No cleanup needed"
        }
    except Exception as e:
        logger.error(f"Error running manual cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/storage/deletion-history")
async def get_deletion_history(limit: int = 100, camera: str = None):
    """Get history of deleted recordings"""
    try:
        # Use camera parameter as camera_id for lookups
        history = playback_db.get_deletion_history(limit=limit, camera_id=camera)

        # Format for display
        formatted = []
        for entry in history:
            formatted.append({
                'id': entry['id'],
                'camera_name': entry['camera_name'],
                'file_path': entry['file_path'],
                'file_size_mb': round(entry['file_size_bytes'] / (1024 * 1024), 1) if entry['file_size_bytes'] else 0,
                'recording_start': entry['recording_start'],
                'recording_end': entry['recording_end'],
                'deletion_reason': entry['deletion_reason'],
                'deleted_at': entry['deleted_at']
            })

        return {'history': formatted}
    except Exception as e:
        logger.error(f"Error getting deletion history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/storage/deletion-stats")
async def get_deletion_stats():
    """Get deletion statistics"""
    try:
        stats = playback_db.get_deletion_stats()

        return {
            'total': {
                'files': stats['total_files'],
                'size_gb': round(stats['total_bytes'] / (1024**3), 2) if stats['total_bytes'] else 0
            },
            'last_24h': {
                'files': stats['last_24h_files'],
                'size_gb': round(stats['last_24h_bytes'] / (1024**3), 2) if stats['last_24h_bytes'] else 0
            },
            'last_7d': {
                'files': stats['last_7d_files'],
                'size_gb': round(stats['last_7d_bytes'] / (1024**3), 2) if stats['last_7d_bytes'] else 0
            }
        }
    except Exception as e:
        logger.error(f"Error getting deletion stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alerts")
async def get_alerts(limit: int = 50):
    """Get recent system alerts"""
    if not alert_system:
        return {'alerts': []}

    return {'alerts': alert_system.get_recent_alerts(limit)}


@app.get("/api/alerts/camera/{camera_id}")
async def get_camera_alerts(camera_id: str, limit: int = 20):
    """Get recent alerts for a specific camera"""
    if not alert_system:
        return {'alerts': []}

    # Look up camera name for backward compatibility with alert system
    recorder = recorder_manager.get_recorder_by_id(camera_id) if recorder_manager else None
    camera_name = recorder.camera_name if recorder else camera_id

    return {'alerts': alert_system.get_alerts_by_camera(camera_name, limit)}


@app.get("/api/motion/heatmap/{camera_id}")
async def get_motion_heatmap(camera_id: str, date: str = None):
    """
    Get motion heatmap for a camera

    Args:
        camera_id: ID of camera
        date: Date in YYYY-MM-DD format (defaults to today)
    """
    try:
        from nvr.core.motion_heatmap import MotionHeatmapManager

        # Parse date
        if date:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        else:
            target_date = datetime.now()

        # Look up camera name for backward compatibility with heatmap manager
        recorder = recorder_manager.get_recorder_by_id(camera_id) if recorder_manager else None
        camera_name = recorder.camera_name if recorder else camera_id

        # Create heatmap manager
        heatmap_mgr = MotionHeatmapManager(config.storage_path, playback_db)

        # Generate daily heatmap
        heatmap_path = heatmap_mgr.get_daily_heatmap(camera_name, target_date)

        if not heatmap_path or not heatmap_path.exists():
            raise HTTPException(status_code=404, detail="No motion data available for this date")

        return FileResponse(
            heatmap_path,
            media_type="image/png",
            filename=f"{camera_name}_heatmap_{date or 'today'}.png"
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        logger.error(f"Error generating heatmap: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint with actual system checks"""
    import psutil
    import time

    status = 'healthy'
    checks = {}

    # Database check
    try:
        if playback_db:
            with playback_db._get_connection() as conn:
                conn.execute("SELECT 1")
            checks['database'] = 'ok'
        else:
            checks['database'] = 'not_initialized'
            status = 'degraded'
    except Exception as e:
        checks['database'] = f'error: {e}'
        status = 'degraded'

    # Disk usage check
    try:
        disk = psutil.disk_usage(str(config.storage_path))
        checks['disk_percent'] = round(disk.percent, 1)
        checks['disk_free_gb'] = round(disk.free / (1024**3), 1)
        if disk.percent > 95:
            status = 'degraded'
    except Exception:
        checks['disk_percent'] = None
        status = 'degraded'

    # Recorder stats
    active_recorders = 0
    if recorder_manager:
        active_recorders = len([r for r in recorder_manager.recorders.values() if r.is_recording])

    # Uptime (process start time)
    try:
        process = psutil.Process()
        uptime_seconds = int(time.time() - process.create_time())
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        checks['uptime'] = f'{hours}h {minutes}m {seconds}s'
    except Exception:
        checks['uptime'] = 'unknown'

    return {
        'status': status,
        'cameras': len(config.cameras),
        'recording': active_recorders,
        'checks': checks
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
        disk = psutil.disk_usage(str(config.storage_path))
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


@app.get("/api/system/encoder")
async def get_encoder_status():
    """Get hardware acceleration encoder status"""
    from nvr.core.transcoder import get_transcoder

    try:
        transcoder = get_transcoder()

        # Determine if GPU acceleration is enabled
        is_gpu = transcoder.encoder not in ('libx264', 'libx265')

        return {
            'encoder': transcoder.encoder,
            'encoder_type': 'GPU' if is_gpu else 'CPU',
            'encoder_options': transcoder.encoder_options,
            'max_workers': transcoder.max_workers,
            'queue_size': transcoder.transcode_queue.qsize() if transcoder.transcode_queue else 0,
            'description': _get_encoder_description(transcoder.encoder)
        }
    except Exception as e:
        logger.error(f"Error getting encoder status: {e}")
        return {
            'encoder': 'unknown',
            'encoder_type': 'CPU',
            'encoder_options': [],
            'max_workers': 0,
            'queue_size': 0,
            'description': 'Transcoder not initialized'
        }


def _get_encoder_description(encoder: str) -> str:
    """Get human-readable description of encoder"""
    descriptions = {
        'h264_nvenc': 'NVIDIA GPU Hardware Acceleration (NVENC)',
        'h264_qsv': 'Intel QuickSync Hardware Acceleration',
        'h264_videotoolbox': 'Apple VideoToolbox Hardware Acceleration',
        'h264_amf': 'AMD GPU Hardware Acceleration (AMF)',
        'libx264': 'CPU Software Encoding (x264)',
        'libx265': 'CPU Software Encoding (x265)'
    }
    return descriptions.get(encoder, f'Unknown encoder: {encoder}')


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


@app.get("/api/cameras/{camera_id}/stream/direct")
async def direct_rtsp_stream(camera_id: str):
    """
    ULTRA-FAST Direct RTSP proxy - ZERO Python processing

    This bypasses ALL frame processing and streams H.264 directly from camera
    Latency: 50-100ms (10-30x faster than any other method)

    Uses FFmpeg to proxy RTSP→HTTP with zero re-encoding
    Browser plays native H.264 stream
    """
    if not rtsp_proxy:
        raise HTTPException(status_code=500, detail="RTSP proxy not initialized")

    # Find camera config by id or name
    cameras = config.cameras
    camera_config = next((c for c in cameras if c.get('id') == camera_id or c['name'] == camera_id), None)

    if not camera_config:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")

    rtsp_url = camera_config['rtsp_url']
    camera_name = camera_config['name']

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


@app.get("/api/cameras/{camera_id}/stream/mse")
async def mse_stream(camera_id: str):
    """
    Media Source Extensions streaming - native browser decoder
    Even lower latency than MPEG-TS
    """
    if not mse_proxy:
        raise HTTPException(status_code=500, detail="MSE proxy not initialized")

    cameras = config.cameras
    camera_config = next((c for c in cameras if c.get('id') == camera_id or c['name'] == camera_id), None)

    if not camera_config:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")

    rtsp_url = camera_config['rtsp_url']
    camera_name = camera_config['name']

    logger.info(f"Starting MSE stream for {camera_name}")

    return StreamingResponse(
        mse_proxy.stream_mse(rtsp_url),
        media_type="video/mp4",
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff"
        }
    )