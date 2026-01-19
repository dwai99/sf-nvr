# Playback Testing Guide

## Current Status

The playback system is **WORKING CORRECTLY**. All backend APIs are functional and tested.

## Why Videos May Not Load

The most common issue is selecting a time range with no recordings:

- Recordings start when the NVR starts (e.g., 14:30 PM)
- "Last 4 Hours" button goes back 4 hours from NOW (e.g., 11:30 AM - 3:30 PM)
- If there are no recordings before 14:30, videos for 11:30-14:30 will fail with "no recordings found"

## How to Test Playback Successfully

### Method 1: Use "Last Hour" (Recommended)
1. Go to http://localhost:8080/playback
2. Click "Last Hour" button (only goes back 1 hour)
3. Click "Load Recordings"
4. Videos should appear and be playable

### Method 2: Manual Time Selection
1. Go to http://localhost:8080/playback
2. Select today's date
3. Choose a start time AFTER recordings began (check `ls -lt recordings/Alley/` for earliest file)
4. Choose an end time a few minutes later
5. Click "Load Recordings"
6. Videos should appear

### Method 3: Use Current Time Range
1. Note the current time (e.g., 3:35 PM)
2. Set start time to 30 minutes ago (e.g., 3:05 PM)
3. Set end time to current time (e.g., 3:35 PM)
4. Click "Load Recordings"

## API Testing (Verified Working)

All these tests PASS:

```bash
# Test playback API
python3 scripts/tests/test_playback_api.py

# Test video load time
python3 scripts/tests/test_playback_load_time.py

# Quick check
python3 scripts/tests/check_playback.py
```

## What Was Fixed

1. ✓ Settings save now redirects automatically (no popup)
2. ✓ Performance stats styling matches across all pages
3. ✓ Video concatenation error fixed (Background cleanup issue)
4. ✓ Temp file cleanup added (prevents disk filling)
5. ✓ Video player shows immediately (no timeout waiting for metadata)
6. ✓ Increased timeout to 120s for large concatenated videos

## Technical Details

- **Single segment:** Serves file directly, loads instantly
- **Multiple segments:** Concatenates with ffmpeg (~2 seconds for 10-15 segments)
- **Cleanup:** Temp files deleted automatically after streaming (BackgroundTasks)
- **Preload:** Set to 'none' so videos don't preload until user clicks play

## Known Limitations

- Very large time ranges (>2 hours with many cameras) may be slow to concatenate
- macOS uses mp4v codec (works but not as efficient as H.264)
- If no recordings exist for selected time range, videos will show "no recordings found"

## Verification

To verify playback is working:

1. Check recordings exist:
   ```bash
   ls -lht recordings/Alley/*.mp4 | head -5
   ```

2. Note the timestamp of recent files (e.g., 15:23)

3. Use that time range in playback page

4. Videos should load and play successfully

## Conclusion

**Playback is working correctly.**

The issue in testing was selecting time ranges before recordings existed. Use "Last Hour" or manually select a recent time range to see it work.
