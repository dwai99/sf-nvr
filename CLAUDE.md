# NVR Project

Network Video Recorder system with web-based playback and live viewing.

## Quick Start

```bash
# Run the server
python -m nvr.app

# Run tests
pytest

# Run specific test file
pytest tests/test_file.py -v
```

## Architecture

```
nvr/
├── app.py              # Flask application entry point
├── core/
│   ├── recorder.py     # Camera recording logic
│   ├── transcoder.py   # FFmpeg video processing
│   ├── motion.py       # Motion detection
│   ├── playback_db.py  # Recording segment database
│   └── recording_modes.py  # Schedule-based recording
├── web/
│   ├── api.py          # Main API endpoints
│   ├── playback_api.py # Playback/streaming endpoints
│   └── recording_api.py # Recording mode endpoints
├── templates/
│   ├── index.html      # Live view page
│   ├── playback.html   # Playback page (complex - has timeline, seeking, multi-camera sync)
│   └── settings.html   # Settings page
└── static/
    ├── notifications.js
    ├── timeline-selector.js
    └── ui-utils.js
```

## Key Technical Details

### Video Pipeline
- Cameras accessed via RTSP
- FFmpeg handles recording and transcoding
- Hardware acceleration: NVIDIA h264_nvenc when available
- Recordings stored as 5-minute MP4 segments
- HLS used for web playback

### Time Handling
- All times are LOCAL (America/Chicago timezone)
- No UTC conversion in frontend - treat all timestamps as local
- Segment filenames contain timestamps in local time

### Playback System (playback.html)
- Timeline shows all segments for selected time range
- Click timeline to seek - calculates position within entire range, not just current segment
- Multiple cameras can be synchronized
- Motion events shown as markers on timeline

## Conventions

- Python 3.x with type hints where practical
- Flask for web framework
- Jinja2 templates with inline JavaScript (no build step)
- Use `console.log` for debug output in JS (remove before committing)

## Common Issues

### Timeline seeking jumps to wrong position
- Ensure percentage is calculated from timeline range, not video segment duration
- Check that segment start time is correctly extracted from video source URL

### Timestamp flickering
- Don't add timezone offsets to timestamps
- Parse all times as local, format as local

## Hardware Requirements

- NVIDIA GPU for hardware transcoding (optional but recommended)
- Sufficient storage for continuous recording
- Network access to RTSP camera streams

## Users

- 3 users currently
- Future: Mobile app planned (Flutter + Tailscale) - see docs/MOBILE_APP_ROADMAP.md
