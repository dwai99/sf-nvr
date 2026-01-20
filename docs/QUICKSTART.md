# Quick Start Guide

## Automated Setup (Recommended)

### macOS/Linux:
```bash
./setup.sh
```

### Windows:
```bash
setup.bat
```

The setup script will:
1. Check for Python and FFmpeg
2. Create a virtual environment
3. Install all dependencies
4. Create configuration files

## Manual Setup

### 1. Create Virtual Environment
```bash
python3 -m venv venv
```

### 2. Activate Virtual Environment

**macOS/Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

Your prompt should now show `(venv)` at the beginning.

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Install FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**Windows:**
- Download from [ffmpeg.org](https://ffmpeg.org/download.html)
- Extract and add to system PATH

## Running the NVR

### Easy Method (One Command)

```bash
./run.sh              # Start NVR
./run.sh discover     # Discover cameras
./run.sh test         # Test discovery
./run.sh fix-onvif    # Fix ONVIF if needed
```

### Manual Method

**Activate virtual environment:**
```bash
source activate_venv.sh
# or manually:
source venv/bin/activate
```

**Start the application:**
```bash
python main.py
```

Access the web interface at: **http://localhost:8080**

### Stop the Application

Press `Ctrl+C` in the terminal

## First Time Configuration

### Option 1: Quick Discovery Tool (Recommended)

Use the standalone discovery tool to find cameras:

```bash
# With virtual environment activated
python discover_cameras.py
```

This will:
- Scan your network for ONVIF cameras
- Show detailed camera information
- Optionally save cameras to config.yaml

### Option 2: Web Interface Discovery

1. Start the NVR: `python main.py`
2. Open http://localhost:8080
3. Click "Discover Cameras"
4. Wait for cameras to be found
5. Cameras will start recording automatically

### Option 3: Manual Configuration

Edit `config/config.yaml`:

```yaml
cameras:
  - name: "My Camera"
    rtsp_url: "rtsp://username:password@192.168.1.100:554/stream1"
    enabled: true
```

Common RTSP URL formats:
- Generic: `rtsp://username:password@IP:554/stream1`
- Hikvision: `rtsp://username:password@IP:554/Streaming/Channels/101`
- Dahua: `rtsp://username:password@IP:554/cam/realmonitor?channel=1&subtype=0`
- Reolink: `rtsp://username:password@IP:554/h264Preview_01_main`

## Daily Usage

### Start Recording
```bash
# Activate virtual environment (if not already active)
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate     # Windows

# Start NVR
python main.py
```

### Stop Recording
Press `Ctrl+C`

### Deactivate Virtual Environment
```bash
deactivate
```

## File Locations

- **Recordings**: `recordings/` - Organized by camera name
- **Configuration**: `config/config.yaml` - Settings
- **Credentials**: `.env` - Default camera username/password
- **Logs**: `nvr.log` - Application logs

## Common Settings

Edit `config/config.yaml`:

```yaml
recording:
  segment_duration: 300     # Seconds per file (300 = 5 min)
  retention_days: 7         # Keep recordings for 7 days

motion_detection:
  enabled: true             # Enable/disable motion detection
  sensitivity: 25           # 0-100, higher = more sensitive

web:
  port: 8080               # Web interface port
```

## Troubleshooting

### "Module not found" error
Make sure virtual environment is activated:
```bash
source venv/bin/activate  # macOS/Linux
```

### Cannot find cameras
1. Ensure cameras are on same network
2. Check firewall settings
3. Try manual configuration with RTSP URL
4. Verify ONVIF is enabled on camera

### High CPU usage
- Lower the resolution in camera settings
- Disable motion detection: `motion_detection.enabled: false`
- Reduce number of simultaneous cameras

### No video showing
1. Verify RTSP URL is correct
2. Test with VLC: Open Network Stream with RTSP URL
3. Check camera username/password
4. Ensure FFmpeg is installed

## Next Steps

- Review full [README.md](README.md) for detailed documentation
- Configure retention policies and motion detection
- Set up multiple cameras
- Customize web interface port and settings

## Getting Help

Check the logs:
```bash
tail -f nvr.log
```

Test camera connection with VLC or ffplay:
```bash
ffplay "rtsp://username:password@IP:554/stream1"
```