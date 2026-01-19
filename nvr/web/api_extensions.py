"""Additional API endpoints for camera management"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging
from nvr.core.config import config

logger = logging.getLogger(__name__)

router = APIRouter()


class CameraRename(BaseModel):
    """Request model for renaming a camera"""
    old_name: str
    new_name: str


class CameraUpdate(BaseModel):
    """Request model for updating camera properties"""
    name: Optional[str] = None
    enabled: Optional[bool] = None
    rtsp_url: Optional[str] = None


@router.post("/api/cameras/{camera_name}/rename")
async def rename_camera(camera_name: str, rename: CameraRename):
    """Rename a camera - updates both config and running recorder"""
    from nvr.web.api import recorder_manager

    logger.info(f"Rename request received: camera_name={camera_name}, rename={rename}")

    try:
        # Validate names
        old_name = rename.old_name
        new_name = rename.new_name

        if not new_name or not new_name.strip():
            raise HTTPException(status_code=400, detail="New name cannot be empty")

        # Find camera in config
        cameras = config.cameras
        camera_found = False

        logger.debug(f"Searching for camera '{old_name}' in {len(cameras)} cameras")

        for camera in cameras:
            if camera['name'] == old_name:
                logger.info(f"Found camera '{old_name}', renaming to '{new_name}'")
                camera['name'] = new_name
                camera_found = True
                break

        if not camera_found:
            logger.warning(f"Camera '{old_name}' not found in config")
            raise HTTPException(status_code=404, detail=f"Camera '{old_name}' not found")

        # Save config
        logger.debug("Saving config...")
        config.save()
        logger.info("Config saved successfully")

        # Update recorder if it exists
        if recorder_manager:
            recorder = recorder_manager.get_recorder(old_name)
            if recorder:
                logger.info(f"Updating recorder name from '{old_name}' to '{new_name}'")
                recorder.camera_name = new_name
                # Update the recorder manager's dictionary key
                recorder_manager.recorders[new_name] = recorder_manager.recorders.pop(old_name)
                logger.info("Recorder updated successfully")

        logger.info(f"Renamed camera: {old_name} → {new_name}")

        return {
            'success': True,
            'message': f'Renamed to {new_name}',
            'new_name': new_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error renaming camera: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/api/cameras/{camera_name}")
async def update_camera(camera_name: str, update: CameraUpdate):
    """Update camera properties"""
    from nvr.core.config import config

    try:
        # Find and update camera
        cameras = config.cameras
        camera_found = False

        for camera in cameras:
            if camera['name'] == camera_name:
                if update.name:
                    camera['name'] = update.name
                if update.enabled is not None:
                    camera['enabled'] = update.enabled
                if update.rtsp_url:
                    camera['rtsp_url'] = update.rtsp_url
                camera_found = True
                break

        if not camera_found:
            raise HTTPException(status_code=404, detail="Camera not found")

        config.save()

        return {'success': True, 'message': 'Camera updated'}

    except Exception as e:
        logger.error(f"Error updating camera: {e}")
        raise HTTPException(status_code=500, detail=str(e))
