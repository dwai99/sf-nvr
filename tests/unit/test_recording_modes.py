"""Unit tests for recording schedules — boundary correctness."""

import pytest
from datetime import datetime

from nvr.core.recording_modes import create_weekend_schedule


@pytest.mark.unit
class TestScheduleBoundary:
    """24/7-style presets must cover the final minute before midnight."""

    def test_no_gap_before_midnight(self):
        sched = create_weekend_schedule()  # end is 23:59:59, all days
        # A Saturday at 23:59:30 must be inside the range (was excluded when end=23:59:00)
        sat_late = datetime(2026, 6, 6, 23, 59, 30)  # 2026-06-06 is a Saturday
        assert sched.is_active(sat_late) is True
