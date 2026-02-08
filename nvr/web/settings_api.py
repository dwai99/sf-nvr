"""
Settings API endpoints for managing system configuration
"""

import logging
from pathlib import Path
from typing import Dict, Any

import psutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nvr.core.config import config

logger = logging.getLogger(__name__)

router = APIRouter()


class ConfigUpdate(BaseModel):
    """Model for configuration updates"""
    recording: Dict[str, Any] = None
    motion_detection: Dict[str, Any] = None
    ai_detection: Dict[str, Any] = None
    web: Dict[str, Any] = None
    onvif: Dict[str, Any] = None
    storage: Dict[str, Any] = None
    cameras: list = None


@router.get("/api/config")
async def get_config():
    """Get current configuration"""
    return {
        "recording": config.get('recording', {}),
        "motion_detection": config.get('motion_detection', {}),
        "ai_detection": config.get('ai_detection', {}),
        "web": config.get('web', {}),
        "onvif": config.get('onvif', {}),
        "storage": config.get('storage', {}),
        "cameras": config.cameras or []
    }


@router.post("/api/config")
async def update_config(updates: ConfigUpdate):
    """Update configuration and save to file"""
    try:
        # Update recording settings
        if updates.recording:
            config.set('recording', updates.recording)

        # Update motion detection settings
        if updates.motion_detection:
            config.set('motion_detection', updates.motion_detection)

        # Update AI detection settings
        if updates.ai_detection:
            config.set('ai_detection', updates.ai_detection)

        # Update web settings
        if updates.web:
            config.set('web', updates.web)

        # Update ONVIF settings
        if updates.onvif:
            config.set('onvif', updates.onvif)

        # Update storage settings
        if updates.storage:
            config.set('storage', updates.storage)

        # Update cameras list
        if updates.cameras is not None:
            config.set('cameras', updates.cameras)

        # Save configuration to file
        config.save()

        logger.info("Configuration updated successfully")
        return {"success": True, "message": "Configuration saved"}

    except Exception as e:
        logger.error(f"Error updating configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/system/storage")
async def get_storage_info():
    """Get storage information for the recordings directory"""
    try:
        storage_path = config.storage_path
        if not storage_path.exists():
            storage_path = Path(".")

        usage = psutil.disk_usage(str(storage_path))

        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": usage.percent,
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2)
        }

    except Exception as e:
        logger.error(f"Error getting storage info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/system/info")
async def get_system_info():
    """Get system information (CPU, memory, etc.)"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()

        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "memory_total_gb": round(memory.total / (1024**3), 2)
        }

    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class MotionSettings(BaseModel):
    """Model for per-camera motion detection settings"""
    sensitivity: int
    min_area: int


class CameraRecordingSettings(BaseModel):
    """Model for per-camera recording settings"""
    resolution: int = None  # 360, 480, 720, or 1080
    recording_mode: str = None  # continuous, motion_only, scheduled, motion_scheduled


@router.get("/api/cameras/{camera_id}/recording-settings")
async def get_camera_recording_settings(camera_id: str):
    """Get recording settings for a specific camera"""
    try:
        for camera in config.cameras:
            if camera.get('id') == camera_id or camera['name'] == camera_id:
                return {
                    'camera_id': camera.get('id'),
                    'camera_name': camera['name'],
                    'resolution': camera.get('resolution', config.get('recording.max_resolution', 720)),
                    'recording_mode': camera.get('recording_mode', 'continuous')
                }

        raise HTTPException(status_code=404, detail="Camera not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recording settings for {camera_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/cameras/{camera_id}/recording-settings")
async def update_camera_recording_settings(camera_id: str, settings: CameraRecordingSettings):
    """Update recording settings for a specific camera

    Note: Changes take effect after server restart.
    """
    try:
        # Validate resolution
        if settings.resolution is not None and settings.resolution not in [360, 480, 720, 1080]:
            raise HTTPException(status_code=400, detail="Invalid resolution. Must be 360, 480, 720, or 1080")

        # Validate recording mode
        valid_modes = ['continuous', 'motion_only', 'scheduled', 'motion_scheduled']
        if settings.recording_mode is not None and settings.recording_mode not in valid_modes:
            raise HTTPException(status_code=400, detail=f"Invalid recording mode. Must be one of: {valid_modes}")

        # Find and update the camera
        camera_found = False
        camera_name = camera_id
        for camera in config.cameras:
            if camera.get('id') == camera_id or camera['name'] == camera_id:
                if settings.resolution is not None:
                    camera['resolution'] = settings.resolution
                if settings.recording_mode is not None:
                    camera['recording_mode'] = settings.recording_mode
                camera_name = camera['name']
                camera_found = True
                break

        if not camera_found:
            raise HTTPException(status_code=404, detail="Camera not found")

        # Save updated config
        config.save_config()

        # Update recording mode manager if running
        if settings.recording_mode:
            try:
                from nvr.web.api import recording_mode_manager
                from nvr.core.recording_modes import RecordingMode
                if recording_mode_manager:
                    mode = RecordingMode(settings.recording_mode)
                    recording_mode_manager.set_camera_mode(camera_name, mode)
                    logger.info(f"Updated recording mode manager for {camera_name}: {mode.value}")
            except Exception as e:
                logger.warning(f"Could not update recording mode manager: {e}")

        logger.info(f"Updated recording settings for {camera_name}: resolution={settings.resolution}, mode={settings.recording_mode}")

        return {
            'success': True,
            'message': f'Recording settings updated for {camera_name}',
            'requires_restart': settings.resolution is not None  # Resolution changes need restart
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating recording settings for {camera_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/cameras/recording-settings")
async def get_all_camera_recording_settings():
    """Get recording settings for all cameras"""
    try:
        default_resolution = config.get('recording.max_resolution', 720)
        results = []

        for camera in config.cameras:
            results.append({
                'camera_id': camera.get('id'),
                'camera_name': camera['name'],
                'resolution': camera.get('resolution', default_resolution),
                'recording_mode': camera.get('recording_mode', 'continuous'),
                'enabled': camera.get('enabled', True)
            })

        return {
            'cameras': results,
            'default_resolution': default_resolution
        }

    except Exception as e:
        logger.error(f"Error getting all recording settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/cameras/{camera_id}/motion-settings")
async def update_camera_motion_settings(camera_id: str, settings: MotionSettings):
    """Update motion detection settings for a specific camera"""
    try:
        # Find the camera in config by id (or name for backward compatibility)
        camera_found = False
        camera_name = camera_id
        for camera in config.cameras:
            if camera.get('id') == camera_id or camera['name'] == camera_id:
                camera['motion_sensitivity'] = settings.sensitivity
                camera['motion_min_area'] = settings.min_area
                camera_name = camera['name']
                camera_found = True
                break

        if not camera_found:
            raise HTTPException(status_code=404, detail="Camera not found")

        # Save updated config to file
        config.save_config()

        logger.info(f"Updated motion settings for {camera_name}: sensitivity={settings.sensitivity}, min_area={settings.min_area}")

        return {
            'success': True,
            'message': f'Motion settings updated for {camera_name}'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating motion settings for {camera_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
