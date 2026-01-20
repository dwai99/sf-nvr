# Time Offset Investigation

## Problem Description
When clicking on the playback timeline, the camera's burned-in timestamp overlay shows a time that is approximately 10 minutes later than the time that was clicked.

## Investigation Steps

### 1. Check Server Time
```bash
$ date && date -u
Mon Jan 19 20:10:44 CST 2026
Tue Jan 20 02:10:44 UTC 2026
```
Server is correctly configured in CST (UTC-6).

### 2. Check Segment Times in Database
```sql
SELECT file_path, start_time, end_time, duration_seconds
FROM recording_segments
WHERE camera_id = 'Patio' AND end_time IS NOT NULL
ORDER BY start_time DESC LIMIT 3;

recordings/Patio/20260119_200022.mp4|2026-01-19 20:00:22.537974|2026-01-19 20:08:20.404008|477
recordings/Patio/20260119_194911.mp4|2026-01-19 19:49:11.761660|2026-01-19 20:00:22.532366|670
recordings/Patio/20260119_194100.mp4|2026-01-19 19:41:00.161105|2026-01-19 19:49:11.756741|491
```

**Observation**:
- File `20260119_200022.mp4` has start_time `20:00:22` (8:00:22 PM)
- This matches the filename timestamp
- Segments are NOT clock-aligned (should be :00, :05, :10, :15, etc.)
- The recorder is using actual recording start times, not clock boundaries

### 3. Why Segments Aren't Clock-Aligned

The recorder code has clock-alignment logic (lines 290-299 in recorder.py):
```python
boundary_minutes = (minutes_since_midnight // segment_minutes) * segment_minutes
self.current_segment_start = datetime(now.year, now.month, now.day, boundary_hour, boundary_minute, 0)
```

However, the server was started BEFORE this code was added (process running since 7:12 PM). All currently recording segments are using the OLD code that just timestamps files with the actual recording start time.

### 4. Playback Code Assumptions

The playback JavaScript (`seekToTime` function) correctly:
1. Finds the segment containing the clicked timestamp
2. Calculates offset: `(clickedTime - segmentStartTime) / 1000` seconds
3. Seeks the video to that offset

**This should work correctly regardless of clock alignment!**

### 5. Possible Causes of 10-Minute Offset

1. **Timezone mismatch**:
   - Server records in CST
   - JavaScript interprets datetime strings without timezone info
   - `new Date("2026-01-19 20:00:22")` interprets in browser's local timezone

2. **Camera clock offset**:
   - Camera's internal clock might be 10 minutes fast/slow
   - Burned-in timestamp comes from camera, not from NVR

3. **Segment boundary confusion**:
   - If timeline shows time X but actual video starts at X+10min
   - Would happen if segments don't cover expected time range

### 6. Next Steps to Diagnose

1. Add console logging to show:
   - Clicked timeline position (timestamp)
   - Found segment start/end times
   - Calculated offset
   - Video actual currentTime after seek

2. Check camera clock vs server clock:
   ```bash
   # Compare NVR server time to camera's burned-in overlay
   ```

3. Restart server with clock-aligned code to see if issue persists with properly aligned segments

## Hypothesis

The most likely cause is #2: **The camera's internal clock is off by 10 minutes**. This would explain why:
- The NVR records the video at the correct time (verified by database timestamps)
- The playback seeks to the correct offset in the video file
- But the camera's burned-in overlay shows incorrect time (burned-in at recording time)

**Solution**: Synchronize camera clocks with NTP or manually adjust them.

## Temporary Workaround

If camera clocks can't be fixed, users can:
1. Note the time offset for each camera
2. Mentally adjust when reviewing footage
3. Or: Add a per-camera time offset setting in the UI
