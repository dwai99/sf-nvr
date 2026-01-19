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

        # Update cameras list
        if updates.cameras is not None:
            config.cameras = updates.cameras

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
        recording_config = config.get('recording', {})
        storage_path = Path(recording_config.get('storage_path', './recordings'))
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
