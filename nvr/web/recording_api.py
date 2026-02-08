"""API endpoints for recording mode management"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import time

logger = logging.getLogger(__name__)

router = APIRouter()


class TimeRangeModel(BaseModel):
    """Time range for scheduled recording"""
    start_hour: int
    start_minute: int = 0
    end_hour: int
    end_minute: int = 0
    days: List[int]  # 0=Monday, 6=Sunday


class RecordingModeConfig(BaseModel):
    """Recording mode configuration for a camera"""
    mode: str  # continuous, motion_only, scheduled, motion_scheduled
    schedules: Optional[List[TimeRangeModel]] = None
    pre_motion_seconds: int = 5
    post_motion_seconds: int = 10
    motion_timeout: int = 5


class RecordingModeUpdate(BaseModel):
    """Update recording mode for a camera"""
    camera_name: str
    config: RecordingModeConfig


@router.get("/api/recording/modes")
async def get_recording_modes():
    """Get recording modes for all cameras"""
    try:
        from nvr.web.api import recording_mode_manager

        if not recording_mode_manager:
            raise HTTPException(status_code=503, detail="Recording mode manager not initialized")

        modes = {}
        for camera_name, config in recording_mode_manager.camera_configs.items():
            schedules = []
            if config.schedules:
                for schedule in config.schedules:
                    schedules.append({
                        'start_hour': schedule.start.hour,
                        'start_minute': schedule.start.minute,
                        'end_hour': schedule.end.hour,
                        'end_minute': schedule.end.minute,
                        'days': schedule.days
                    })

            modes[camera_name] = {
                'mode': config.mode.value,
                'schedules': schedules,
                'pre_motion_seconds': config.pre_motion_seconds,
                'post_motion_seconds': config.post_motion_seconds,
                'motion_timeout': config.motion_timeout
            }

        # Add default config
        default_schedules = []
        if recording_mode_manager.default_config.schedules:
            for schedule in recording_mode_manager.default_config.schedules:
                default_schedules.append({
                    'start_hour': schedule.start.hour,
                    'start_minute': schedule.start.minute,
                    'end_hour': schedule.end.hour,
                    'end_minute': schedule.end.minute,
                    'days': schedule.days
                })

        return {
            'success': True,
            'default_mode': {
                'mode': recording_mode_manager.default_config.mode.value,
                'schedules': default_schedules,
                'pre_motion_seconds': recording_mode_manager.default_config.pre_motion_seconds,
                'post_motion_seconds': recording_mode_manager.default_config.post_motion_seconds,
                'motion_timeout': recording_mode_manager.default_config.motion_timeout
            },
            'camera_modes': modes
        }
    except Exception as e:
        logger.error(f"Error getting recording modes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/recording/modes/{camera_name}")
async def get_camera_recording_mode(camera_name: str):
    """Get recording mode for a specific camera"""
    try:
        from nvr.web.api import recording_mode_manager

        if not recording_mode_manager:
            raise HTTPException(status_code=503, detail="Recording mode manager not initialized")

        config = recording_mode_manager.get_camera_config(camera_name)

        schedules = []
        if config.schedules:
            for schedule in config.schedules:
                schedules.append({
                    'start_hour': schedule.start.hour,
                    'start_minute': schedule.start.minute,
                    'end_hour': schedule.end.hour,
                    'end_minute': schedule.end.minute,
                    'days': schedule.days
                })

        return {
            'success': True,
            'camera_name': camera_name,
            'mode': config.mode.value,
            'schedules': schedules,
            'pre_motion_seconds': config.pre_motion_seconds,
            'post_motion_seconds': config.post_motion_seconds,
            'motion_timeout': config.motion_timeout
        }
    except Exception as e:
        logger.error(f"Error getting recording mode for {camera_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/recording/modes")
async def set_camera_recording_mode(update: RecordingModeUpdate):
    """Set recording mode for a camera"""
    try:
        from nvr.web.api import recording_mode_manager
        from nvr.core.recording_modes import RecordingMode, TimeRange

        if not recording_mode_manager:
            raise HTTPException(status_code=503, detail="Recording mode manager not initialized")

        # Parse mode
        try:
            mode = RecordingMode(update.config.mode)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid recording mode: {update.config.mode}")

        # Parse schedules
        schedules = None
        if update.config.schedules:
            schedules = []
            for sched in update.config.schedules:
                schedules.append(TimeRange(
                    start=time(hour=sched.start_hour, minute=sched.start_minute),
                    end=time(hour=sched.end_hour, minute=sched.end_minute),
                    days=sched.days
                ))

        # Set camera mode
        recording_mode_manager.set_camera_mode(
            camera_name=update.camera_name,
            mode=mode,
            schedules=schedules,
            pre_motion_seconds=update.config.pre_motion_seconds,
            post_motion_seconds=update.config.post_motion_seconds,
            motion_timeout=update.config.motion_timeout
        )

        logger.info(f"Updated recording mode for {update.camera_name}: {mode.value}")

        return {
            'success': True,
            'message': f'Recording mode updated for {update.camera_name}',
            'mode': mode.value
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting recording mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/recording/modes/{camera_name}")
async def reset_camera_recording_mode(camera_name: str):
    """Reset camera to default recording mode"""
    try:
        from nvr.web.api import recording_mode_manager

        if not recording_mode_manager:
            raise HTTPException(status_code=503, detail="Recording mode manager not initialized")

        if camera_name in recording_mode_manager.camera_configs:
            del recording_mode_manager.camera_configs[camera_name]
            logger.info(f"Reset recording mode for {camera_name} to default")

            return {
                'success': True,
                'message': f'Recording mode reset to default for {camera_name}'
            }
        else:
            return {
                'success': True,
                'message': f'{camera_name} was already using default mode'
            }
    except Exception as e:
        logger.error(f"Error resetting recording mode for {camera_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/recording/status")
async def get_recording_status():
    """Get current recording status for all cameras"""
    try:
        from nvr.web.api import recorder_manager, recording_mode_manager
        from datetime import datetime

        if not recorder_manager:
            raise HTTPException(status_code=503, detail="Recorder manager not initialized")

        status = []
        for camera_name, recorder in recorder_manager.recorders.items():
            # Get recording mode config
            config = recording_mode_manager.get_camera_config(camera_name) if recording_mode_manager else None

            should_record = True
            if recording_mode_manager:
                should_record = recording_mode_manager.should_record(
                    camera_name,
                    has_motion=recorder.has_motion,
                    dt=datetime.now()
                )

            status.append({
                'camera_name': camera_name,
                'is_recording': recorder.is_recording,
                'actively_writing': recorder.actively_writing,
                'has_motion': recorder.has_motion,
                'should_record': should_record,
                'mode': config.mode.value if config else 'continuous',
                'last_motion_time': recorder.last_motion_time.isoformat() if recorder.last_motion_time else None
            })

        return {
            'success': True,
            'cameras': status
        }
    except Exception as e:
        logger.error(f"Error getting recording status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
