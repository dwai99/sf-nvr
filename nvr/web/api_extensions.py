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


@router.post("/api/cameras/{camera_id}/rename")
async def rename_camera(camera_id: str, rename: CameraRename):
    """Rename a camera - updates both config and running recorder"""
    from nvr.web.api import recorder_manager

    logger.info(f"Rename request received: camera_id={camera_id}, rename={rename}")

    try:
        # Validate names
        old_name = rename.old_name
        new_name = rename.new_name

        if not new_name or not new_name.strip():
            raise HTTPException(status_code=400, detail="New name cannot be empty")

        # Find camera in config by id (or name for backward compatibility)
        cameras = config.cameras
        camera_found = False
        target_camera = None

        logger.debug(f"Searching for camera with id '{camera_id}' in {len(cameras)} cameras")

        # Check for duplicate name (another camera already has this name)
        for camera in cameras:
            if camera['name'] == new_name and camera.get('id') != camera_id:
                raise HTTPException(status_code=400, detail=f"Another camera already has the name '{new_name}'")

        for camera in cameras:
            if camera.get('id') == camera_id or camera['name'] == camera_id:
                logger.info(f"Found camera '{camera['name']}' (id: {camera.get('id')}), renaming to '{new_name}'")
                camera['name'] = new_name
                camera_found = True
                break

        if not camera_found:
            logger.warning(f"Camera with id '{camera_id}' not found in config")
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")

        # Save config
        logger.debug("Saving config...")
        config.save()
        logger.info("Config saved successfully")

        # Update recorder if it exists
        if recorder_manager:
            recorder = recorder_manager.get_recorder_by_id(camera_id)
            if recorder:
                old_recorder_name = recorder.camera_name
                logger.info(f"Updating recorder name from '{old_recorder_name}' to '{new_name}'")
                recorder.camera_name = new_name
                # Update the recorder manager's dictionary key
                recorder_manager.recorders[new_name] = recorder_manager.recorders.pop(old_recorder_name)
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


@router.patch("/api/cameras/{camera_id}")
async def update_camera(camera_id: str, update: CameraUpdate):
    """Update camera properties"""
    from nvr.core.config import config

    try:
        # Find and update camera by id (or name for backward compatibility)
        cameras = config.cameras
        camera_found = False

        for camera in cameras:
            if camera.get('id') == camera_id or camera['name'] == camera_id:
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
