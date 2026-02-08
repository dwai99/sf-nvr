"""Recording mode management for optimized storage usage"""

import logging
from enum import Enum
from datetime import datetime, time
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class RecordingMode(str, Enum):
    """Recording mode options"""
    CONTINUOUS = "continuous"           # Always recording (24/7)
    MOTION_ONLY = "motion_only"        # Only record when motion detected
    SCHEDULED = "scheduled"            # Record during specific hours
    MOTION_SCHEDULED = "motion_scheduled"  # Motion detection during specific hours


@dataclass
class TimeRange:
    """Represents a time range for scheduled recording"""
    start: time
    end: time
    days: List[int]  # 0=Monday, 6=Sunday

    def is_active(self, dt: Optional[datetime] = None) -> bool:
        """Check if current time is within this range"""
        if dt is None:
            dt = datetime.now()

        # Check if current day is in the schedule
        weekday = dt.weekday()  # 0=Monday, 6=Sunday
        if weekday not in self.days:
            return False

        current_time = dt.time()

        # Handle overnight ranges (e.g., 22:00 to 06:00)
        if self.end < self.start:
            return current_time >= self.start or current_time <= self.end
        else:
            return self.start <= current_time <= self.end


@dataclass
class RecordingConfig:
    """Configuration for a camera's recording behavior"""
    mode: RecordingMode = RecordingMode.CONTINUOUS
    schedules: List[TimeRange] = None  # Used for SCHEDULED and MOTION_SCHEDULED modes
    pre_motion_seconds: int = 5        # Seconds to record before motion event
    post_motion_seconds: int = 10      # Seconds to record after motion ends
    motion_timeout: int = 5            # Seconds of no motion before stopping recording

    def __post_init__(self):
        if self.schedules is None:
            self.schedules = []

    def should_record_now(self, has_motion: bool = False, dt: Optional[datetime] = None) -> bool:
        """
        Determine if recording should be active based on mode and current conditions

        Args:
            has_motion: Whether motion is currently detected
            dt: Datetime to check (defaults to now)

        Returns:
            True if recording should be active
        """
        if dt is None:
            dt = datetime.now()

        if self.mode == RecordingMode.CONTINUOUS:
            # Always record
            return True

        elif self.mode == RecordingMode.MOTION_ONLY:
            # Only record when motion is detected
            return has_motion

        elif self.mode == RecordingMode.SCHEDULED:
            # Record during scheduled hours regardless of motion
            return self._is_in_schedule(dt)

        elif self.mode == RecordingMode.MOTION_SCHEDULED:
            # Only record motion during scheduled hours
            in_schedule = self._is_in_schedule(dt)
            return in_schedule and has_motion

        # Default to continuous if mode is unknown
        logger.warning(f"Unknown recording mode: {self.mode}, defaulting to continuous")
        return True

    def _is_in_schedule(self, dt: datetime) -> bool:
        """Check if datetime is within any configured schedule"""
        if not self.schedules:
            # No schedules defined, default to always active
            return True

        for schedule in self.schedules:
            if schedule.is_active(dt):
                return True

        return False


class RecordingModeManager:
    """Manages recording modes for all cameras"""

    def __init__(self):
        self.camera_configs: Dict[str, RecordingConfig] = {}
        self.default_config = RecordingConfig(mode=RecordingMode.CONTINUOUS)

    def set_camera_mode(
        self,
        camera_name: str,
        mode: RecordingMode,
        schedules: Optional[List[TimeRange]] = None,
        pre_motion_seconds: int = 5,
        post_motion_seconds: int = 10,
        motion_timeout: int = 5
    ):
        """Set recording mode for a specific camera"""
        self.camera_configs[camera_name] = RecordingConfig(
            mode=mode,
            schedules=schedules or [],
            pre_motion_seconds=pre_motion_seconds,
            post_motion_seconds=post_motion_seconds,
            motion_timeout=motion_timeout
        )
        logger.info(f"Set {camera_name} to {mode} mode")

    def get_camera_config(self, camera_name: str) -> RecordingConfig:
        """Get recording configuration for a camera"""
        return self.camera_configs.get(camera_name, self.default_config)

    def should_record(
        self,
        camera_name: str,
        has_motion: bool = False,
        dt: Optional[datetime] = None
    ) -> bool:
        """Check if camera should be recording right now"""
        config = self.get_camera_config(camera_name)
        return config.should_record_now(has_motion, dt)

    def get_all_configs(self) -> Dict[str, RecordingConfig]:
        """Get all camera recording configurations"""
        return self.camera_configs.copy()

    def clear_camera_config(self, camera_name: str):
        """Remove custom config for camera (reverts to default)"""
        if camera_name in self.camera_configs:
            del self.camera_configs[camera_name]
            logger.info(f"Cleared recording mode for {camera_name}, using default")


# Helper functions for creating common schedules

def create_business_hours(
    start_hour: int = 9,
    end_hour: int = 17,
    weekdays_only: bool = True
) -> TimeRange:
    """
    Create a business hours schedule

    Args:
        start_hour: Starting hour (24-hour format)
        end_hour: Ending hour (24-hour format)
        weekdays_only: If True, only Monday-Friday

    Returns:
        TimeRange for business hours
    """
    days = list(range(5)) if weekdays_only else list(range(7))  # 0-4 = Mon-Fri, 0-6 = Mon-Sun
    return TimeRange(
        start=time(hour=start_hour, minute=0),
        end=time(hour=end_hour, minute=0),
        days=days
    )


def create_night_hours(
    start_hour: int = 22,
    end_hour: int = 6,
    all_days: bool = True
) -> TimeRange:
    """
    Create a night hours schedule (handles overnight)

    Args:
        start_hour: Starting hour (24-hour format, e.g., 22 for 10 PM)
        end_hour: Ending hour (24-hour format, e.g., 6 for 6 AM)
        all_days: If True, applies to all days

    Returns:
        TimeRange for night hours
    """
    days = list(range(7)) if all_days else list(range(5))
    return TimeRange(
        start=time(hour=start_hour, minute=0),
        end=time(hour=end_hour, minute=0),
        days=days
    )


def create_weekend_schedule() -> TimeRange:
    """Create a weekend-only schedule (Saturday-Sunday, all day)"""
    return TimeRange(
        start=time(hour=0, minute=0),
        end=time(hour=23, minute=59),
        days=[5, 6]  # Saturday, Sunday
    )


def create_custom_schedule(
    start_hour: int,
    start_minute: int,
    end_hour: int,
    end_minute: int,
    days: List[int]
) -> TimeRange:
    """
    Create a custom time range

    Args:
        start_hour: Starting hour (0-23)
        start_minute: Starting minute (0-59)
        end_hour: Ending hour (0-23)
        end_minute: Ending minute (0-59)
        days: List of weekdays (0=Monday, 6=Sunday)

    Returns:
        TimeRange for the specified schedule
    """
    return TimeRange(
        start=time(hour=start_hour, minute=start_minute),
        end=time(hour=end_hour, minute=end_minute),
        days=days
    )


# Example usage and presets

def get_preset_schedules() -> Dict[str, List[TimeRange]]:
    """Get common preset schedules"""
    return {
        "business_hours": [create_business_hours()],
        "business_hours_extended": [create_business_hours(start_hour=8, end_hour=18)],
        "after_hours": [create_night_hours()],
        "weekends_only": [create_weekend_schedule()],
        "24_7": [TimeRange(
            start=time(hour=0, minute=0),
            end=time(hour=23, minute=59),
            days=list(range(7))
        )]
    }
