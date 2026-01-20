# NVR Scripts Guide

Quick reference for managing your NVR system.

## Daily Operations

### Start the NVR
```bash
./start.sh
```
- Starts server with TCP RTSP transport
- Monitors camera connections for 15 seconds
- Shows which cameras connect successfully
- Best for normal use

### Stop the NVR
```bash
./stop.sh
```
- Graceful shutdown (tries SIGTERM first)
- Force kills after 10 seconds if needed
- Cleans up ports and PID files

### Restart the NVR
```bash
./restart.sh
```
- Stops then starts with full monitoring
- 2 second pause between stop/start

---

## Testing & Diagnostics

### Test Streaming Performance
```bash
./test_streaming.sh
```
Tests MJPEG streaming at different quality levels, measures response times and data rates.

### System Validation
```bash
./discover.sh
```
Runs 11 automated tests covering server health, APIs, cameras, and performance.

### Test Individual Camera
```bash
./test_camera.sh
```
Tests a specific camera's RTSP connection using ffmpeg.

---

## Setup & Utilities

### Initial Setup
```bash
./setup.sh
```
One-time setup: creates virtual environment and installs dependencies.

### Activate Virtual Environment
```bash
source ./activate_venv.sh
```
Activates the Python virtual environment for manual commands.

### Fix ONVIF Issues
```bash
./fix_onvif.sh
```
Reinstalls ONVIF package if camera discovery is broken.

### Download AI Models
```bash
./download_ai_models.sh
```
Downloads models for AI person/vehicle detection (if enabled).

---

## Network Access

The NVR is accessible from any device on your network:

- **Local**: http://localhost:8080
- **Network**: http://192.168.0.50:8080

To access from another computer, phone, or tablet on the same network, use the network URL above.

---

## Troubleshooting

**NVR won't start:**
1. Check if port 8080 is in use: `lsof -i :8080`
2. Check logs: `tail -f /tmp/nvr_server.log`
3. Try force stop first: `./stop.sh`

**High CPU usage:**
- Server was using 300%+ CPU due to frame queue bug (now fixed)
- Normal usage should be under 10% CPU
- If high CPU returns, restart: `./restart.sh`

**Cameras not connecting:**
- Wait 30-60 seconds for retry attempts
- Check camera IP addresses are reachable
- Check RTSP credentials in `config/config.yaml`

**Can't Ctrl+C to stop:**
- Use `./stop.sh` instead
- Or: `kill $(cat /tmp/nvr_server.pid)`

---

## File Locations

- **Config**: `config/config.yaml`
- **Recordings**: `recordings/`
- **Logs**: `/tmp/nvr_server.log`
- **PID file**: `/tmp/nvr_server.pid`
- **Database**: `config/playback.db`

---

## Removed Scripts

These were removed as obsolete (backups in `.old_scripts/`):
- `run.sh` - replaced by enhanced `start.sh`
- `startup_dev.sh` - use `start.sh` instead
- `startup_performance.sh` - use `start.sh` instead
