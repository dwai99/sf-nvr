# Troubleshooting Guide

## Camera Discovery Issues

### "No such file: wsdl/devicemgmt.wsdl" Error

This is a known issue with `onvif-zeep` 0.2.12 from PyPI - the WSDL files are missing.

**Quick Fix:**
```bash
# With virtual environment activated
./fix_onvif.sh
```

**Manual Fix:**
```bash
# Uninstall broken version
pip uninstall -y onvif-zeep

# Install from git (includes WSDL files)
pip install git+https://github.com/FalkTannhaeuser/python-onvif-zeep.git

# Verify
python3 -c "from pathlib import Path; import onvif; print((Path(onvif.__file__).parent / 'wsdl').exists())"
# Should print: True
```

## Camera Discovery Issues

### Discovery is slow or hangs

The discovery process scans your entire subnet. Here's what happens:

**Phase 1: Port Scanning** (Fast)
- Scans 254 IPs × 3 ports = 762 combinations
- Uses 0.5s timeout per check
- Should complete in 10-30 seconds

**Phase 2: ONVIF Testing** (Slower)
- Only tests hosts that responded in Phase 1
- Uses 5s timeout per camera
- Time depends on number of responsive hosts

**Solutions:**

1. **Use the standalone discovery tool** (shows better progress):
   ```bash
   python discover_cameras.py
   ```

2. **Specify a smaller IP range** if you know where cameras are:
   ```bash
   # In discover_cameras.py, enter specific range like:
   192.168.1.100-110
   ```

3. **Reduce discovery timeout** in `config/config.yaml`:
   ```yaml
   onvif:
     discovery_timeout: 3  # Reduce from 5 to 3 seconds
   ```

4. **Check the logs** - you should see progress messages:
   ```
   Phase 1: Quick port scan...
   Scanned 300/762 combinations...
   Scanned 600/762 combinations...
   Found X responsive host(s)
   Phase 2: Testing ONVIF connections...
   Testing 192.168.1.100:80 (1/3)...
   ```

### No cameras found

**Check 1: Network connectivity**
```bash
# Ping your camera
ping 192.168.1.100

# Try accessing camera's web interface
# Open browser to http://192.168.1.100
```

**Check 2: ONVIF enabled**
- Log into camera's web interface
- Look for ONVIF settings (usually in Network or Integration settings)
- Ensure ONVIF is enabled
- Note the ONVIF port (usually 80, 8080, or 8000)

**Check 3: Credentials**
Edit `.env` file:
```bash
DEFAULT_CAMERA_USERNAME=admin
DEFAULT_CAMERA_PASSWORD=your_actual_password
```

**Check 4: Firewall**
```bash
# On camera's network, ensure these ports are open:
# - 80, 8080, 8000 (ONVIF)
# - 554 (RTSP)
```

**Check 5: Subnet**
Ensure your computer and cameras are on the same subnet:
```bash
# Check your IP
ipconfig  # Windows
ifconfig  # macOS/Linux

# If your IP is 192.168.1.50, cameras should be 192.168.1.X
# If your IP is 10.0.0.50, cameras should be 10.0.0.X
```

### Manual camera testing

Test if you can connect to camera manually:

```bash
# Test RTSP stream with ffplay (comes with FFmpeg)
ffplay "rtsp://username:password@192.168.1.100:554/stream1"

# Or with VLC
# File > Open Network Stream
# Enter: rtsp://username:password@192.168.1.100:554/stream1
```

Common RTSP URL patterns:
- Generic: `rtsp://user:pass@IP:554/stream1`
- Hikvision: `rtsp://user:pass@IP:554/Streaming/Channels/101`
- Dahua: `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0`
- Reolink: `rtsp://user:pass@IP:554/h264Preview_01_main`
- Amcrest: `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0`

## Recording Issues

### "Failed to open RTSP stream"

**Solution 1: Verify RTSP URL**
```bash
# Test with ffplay first
ffplay "rtsp://username:password@IP:554/stream"
```

**Solution 2: Check camera limits**
- Most cameras limit simultaneous RTSP connections (usually 3-5)
- Close other viewers (VLC, web browsers, other NVR software)

**Solution 3: Check credentials in URL**
- Ensure username/password are correct
- Some special characters need URL encoding:
  - `@` → `%40`
  - `#` → `%23`
  - `&` → `%26`

### Recording stops after a while

**Solution 1: Check disk space**
```bash
df -h  # Check available disk space
```

**Solution 2: Check logs**
```bash
tail -f nvr.log
```

**Solution 3: Increase retention, decrease segment size**
Edit `config/config.yaml`:
```yaml
recording:
  segment_duration: 180  # Smaller segments (3 min instead of 5)
  retention_days: 3      # Keep less historical data
```

### Video files are corrupted

**Solution 1: Check FFmpeg installation**
```bash
ffmpeg -version
```

**Solution 2: Try different codec**
Edit `config/config.yaml`:
```yaml
recording:
  video_codec: "mpeg4"  # Instead of h264
```

**Solution 3: Check camera stream format**
- Some cameras send corrupt streams
- Try a different stream (main vs sub-stream)
- Update camera firmware

## Motion Detection Issues

### Too many false positives

Edit `config/config.yaml`:
```yaml
motion_detection:
  sensitivity: 35       # Increase from 25 (less sensitive)
  min_area: 1000       # Increase from 500 (larger movements only)
```

### Motion not detected

```yaml
motion_detection:
  sensitivity: 15       # Decrease from 25 (more sensitive)
  min_area: 200        # Decrease from 500 (detect smaller movements)
```

### High CPU usage from motion detection

**Solution 1: Disable for static cameras**
```yaml
motion_detection:
  enabled: false
```

**Solution 2: Check fewer frames**
Edit `nvr/web/api.py` and change `check_interval`:
```python
# Around line 300+
await self.monitor_recorder(camera_name, recorder, check_interval=3)
# Change from 1 to 3 to check every 3rd frame
```

## Web Interface Issues

### Cannot access http://localhost:8080

**Solution 1: Check if server is running**
```bash
# Look for "Uvicorn running on http://0.0.0.0:8080"
```

**Solution 2: Try different address**
```
http://127.0.0.1:8080
http://YOUR-IP-ADDRESS:8080
```

**Solution 3: Change port**
Edit `config/config.yaml`:
```yaml
web:
  port: 8000  # Try different port
```

### Live view not showing

**Solution 1: Check browser console**
- Press F12 in browser
- Look for errors in Console tab

**Solution 2: Check if recording is active**
- Camera must be recording for live view to work
- Click "Start" button for the camera

**Solution 3: Try different browser**
- Chrome/Edge work best
- Safari may have issues with MJPEG streams

## Installation Issues

### "Module not found" error

**Solution: Virtual environment not activated**
```bash
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# You should see (venv) in your prompt
```

### FFmpeg not found

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg libavcodec-dev libavformat-dev libswscale-dev
```

**Windows:**
1. Download from https://ffmpeg.org/download.html
2. Extract to C:\ffmpeg
3. Add C:\ffmpeg\bin to system PATH
4. Restart terminal

### opencv-python installation fails

**Solution 1: Install system dependencies (Linux)**
```bash
sudo apt-get install python3-opencv
# Or
sudo apt-get install libsm6 libxext6 libxrender-dev
pip install opencv-python
```

**Solution 2: Use headless version**
```bash
pip uninstall opencv-python
pip install opencv-python-headless
```

### onvif-zeep installation issues

**Solution: Install zeep dependencies**
```bash
# macOS
brew install libxml2 libxslt

# Ubuntu/Debian
sudo apt-get install libxml2-dev libxslt1-dev

# Then retry
pip install onvif-zeep
```

## Performance Issues

### High CPU usage

**Solutions:**
1. Reduce camera resolution in camera settings
2. Use sub-stream instead of main stream
3. Disable motion detection
4. Record fewer cameras simultaneously
5. Increase segment duration to write files less often

### High disk usage

**Solutions:**
1. Reduce retention: `retention_days: 3`
2. Use smaller segments: `segment_duration: 180`
3. Lower camera resolution
4. Use better compression codec: `video_codec: "h265"`

### System is slow/laggy

**Check resources:**
```bash
# CPU and Memory usage
top         # macOS/Linux
htop        # Linux (better)
taskmgr     # Windows

# Disk I/O
iostat      # macOS/Linux
```

**Solutions:**
1. Move recordings to faster disk (SSD)
2. Reduce number of cameras
3. Use hardware acceleration (requires additional setup)

## Getting More Help

### Enable debug logging

Edit `main.py`:
```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO
    ...
)
```

### Check detailed logs

```bash
# View real-time logs
tail -f nvr.log

# Search for errors
grep ERROR nvr.log
grep -i "failed" nvr.log
```

### Test individual components

```bash
# Test camera discovery
python discover_cameras.py

# Test RTSP stream
ffplay "rtsp://user:pass@IP:554/stream"

# Check Python environment
python -c "import cv2; print(cv2.__version__)"
python -c "import onvif; print('ONVIF OK')"
```

### Capture debug information

```bash
# System info
python --version
ffmpeg -version
uname -a  # macOS/Linux
systeminfo  # Windows

# Network info
ipconfig /all  # Windows
ifconfig -a    # macOS/Linux

# Disk space
df -h  # macOS/Linux
```
