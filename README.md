# SF-NVR - Network Video Recorder

[![CI/CD Pipeline](https://github.com/sfrederick/sf-nvr/actions/workflows/ci.yml/badge.svg)](https://github.com/sfrederick/sf-nvr/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/sfrederick/sf-nvr/branch/main/graph/badge.svg)](https://codecov.io/gh/sfrederick/sf-nvr)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python-based Network Video Recorder (NVR) with support for ONVIF camera discovery and RTSP streaming.

## Features

- **ONVIF Camera Discovery**: Automatically discover IP cameras on your network
- **RTSP Recording**: Continuous recording from multiple RTSP streams
- **Motion Detection**: Real-time motion detection with configurable sensitivity
- **Web Interface**: Modern web UI for live viewing and playback
- **Automatic Retention**: Configurable retention policies for recordings
- **Multi-Camera Support**: Record from multiple cameras simultaneously

## Requirements

- Python 3.8+
- FFmpeg (for video processing)
- OpenCV
- IP cameras supporting ONVIF and/or RTSP

## Installation

### Step 1: Install System Dependencies

First, install FFmpeg (required for video processing):

- **macOS**:
  ```bash
  brew install ffmpeg
  ```

- **Ubuntu/Debian**:
  ```bash
  sudo apt-get update
  sudo apt-get install ffmpeg
  ```

- **Windows**:
  Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH

### Step 2: Create Python Virtual Environment

It's recommended to use a virtual environment to isolate dependencies:

```bash
# Navigate to the project directory
cd sf-nvr

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt when activated.

### Step 3: Install Python Dependencies

With the virtual environment activated:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your camera credentials (optional)
nano .env  # or use your preferred editor
```

### Step 5: Configure Cameras (Optional)

Edit `config/config.yaml` to manually add cameras or adjust settings. You can also use the auto-discovery feature in the web interface.

## Configuration

Edit `config/config.yaml` to configure your NVR:

```yaml
recording:
  storage_path: "./recordings"
  segment_duration: 300  # 5 minutes per file
  retention_days: 7
  video_codec: "h264"
  container_format: "mp4"

motion_detection:
  enabled: true
  sensitivity: 25
  min_area: 500

onvif:
  discovery_timeout: 5
  auto_discover: true

web:
  host: "0.0.0.0"
  port: 8080
```

### Adding Cameras

You can add cameras in two ways:

1. **Automatic Discovery** (ONVIF):
   - Click "Discover Cameras" in the web interface
   - Cameras will be automatically detected and configured

2. **Manual Configuration** in `config/config.yaml`:
```yaml
cameras:
  - name: "Front Door"
    rtsp_url: "rtsp://admin:password@192.168.1.100:554/stream1"
    onvif_host: "192.168.1.100"
    onvif_port: 80
    username: "admin"
    password: "password"
    enabled: true
```

## Usage

### Starting the NVR

**Important**: Always activate your virtual environment first!

```bash
# Activate virtual environment (if not already activated)
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate     # Windows

# Start the NVR
python main.py
```

The web interface will be available at `http://localhost:8080`

### Stopping the NVR

Press `Ctrl+C` in the terminal to gracefully shut down.

### Deactivating Virtual Environment

When you're done:

```bash
deactivate
```

### Web Interface Features

- **Live View**: View live streams from all cameras
- **Recording Control**: Start/stop recording for individual cameras
- **Motion Detection**: Visual indicators when motion is detected
- **Playback**: Browse and play back recorded footage
- **Camera Discovery**: Discover new ONVIF cameras on your network

### API Endpoints

The NVR provides a REST API:

- `GET /api/cameras` - List all cameras
- `POST /api/cameras/discover` - Discover ONVIF cameras
- `POST /api/cameras/{name}/start` - Start recording
- `POST /api/cameras/{name}/stop` - Stop recording
- `GET /api/cameras/{name}/live` - Live MJPEG stream
- `GET /api/cameras/{name}/recordings` - List recordings
- `GET /api/recordings/{name}/{filename}` - Download recording

## Project Structure

```
sf-nvr/
├── nvr/
│   ├── core/
│   │   ├── config.py          # Configuration management
│   │   ├── onvif_discovery.py # ONVIF camera discovery
│   │   ├── recorder.py        # RTSP recording
│   │   └── motion.py          # Motion detection
│   ├── web/
│   │   └── api.py            # FastAPI web application
│   └── templates/
│       └── index.html        # Web interface
├── config/
│   └── config.yaml           # Configuration file
├── recordings/               # Recorded video storage
├── requirements.txt          # Python dependencies
└── main.py                  # Application entry point
```

## Camera Compatibility

This NVR works with any camera that supports:
- **RTSP**: For video streaming
- **ONVIF** (optional): For automatic discovery and configuration

Tested with:
- Hikvision
- Dahua
- Reolink
- Amcrest
- Generic ONVIF cameras

## Storage and Retention

Recordings are stored in the `recordings/` directory, organized by camera name:

```
recordings/
├── Front_Door/
│   ├── 20231215_120000.mp4
│   ├── 20231215_120500.mp4
│   └── ...
└── Back_Yard/
    └── ...
```

Files older than the configured retention period are automatically deleted.

## Motion Detection

Motion detection uses background subtraction to identify movement in the video stream:

- **Sensitivity**: 0-100, higher values detect smaller movements
- **Min Area**: Minimum pixel area to trigger detection
- **Visual Indicators**: Motion areas are highlighted in the live view
- **Event Notifications**: Real-time notifications via WebSocket

## Performance Tips

1. **Segment Duration**: Smaller segments (1-5 min) make it easier to find specific events
2. **Resolution**: Lower resolution streams reduce CPU and storage requirements
3. **Motion Detection**: Disable for static cameras to save CPU
4. **Codec**: H.264 provides good compression with reasonable CPU usage

## Troubleshooting

### Cannot connect to camera
- Verify RTSP URL is correct
- Check camera username/password
- Ensure camera is reachable on network
- Some cameras require enabling RTSP in settings

### High CPU usage
- Reduce number of cameras or lower resolution
- Increase segment duration
- Disable motion detection for some cameras

### ONVIF discovery not finding cameras
- Ensure cameras are on same subnet
- Check firewall settings
- Try manual IP range scan
- Verify ONVIF is enabled on cameras

## Development

To contribute or modify:

1. Install development dependencies:
```bash
pip install -r requirements.txt
```

2. Run with auto-reload:
```bash
uvicorn nvr.web.api:app --reload --host 0.0.0.0 --port 8080
```

## License

This project is open source and available for personal and commercial use.

## Support

For issues, questions, or contributions, please open an issue on the project repository.