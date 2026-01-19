# Quick Command Reference

## Setup (First Time Only)

```bash
# Automated setup
./setup.sh

# Fix ONVIF if you get WSDL errors
./run.sh fix-onvif
```

## Daily Use

### Start NVR
```bash
./run.sh
# Opens web interface at http://localhost:8080
```

### Discover Cameras
```bash
./run.sh discover
```

### Test Discovery
```bash
./run.sh test
```

## Manual Commands

### Activate Virtual Environment
```bash
source activate_venv.sh
# or
source venv/bin/activate
```

### With venv activated:
```bash
python main.py              # Start NVR
python discover_cameras.py  # Discover cameras
python test_discovery.py    # Test discovery
./fix_onvif.sh             # Fix ONVIF
```

## Troubleshooting

### ONVIF WSDL Error
```bash
./run.sh fix-onvif
```

### Check Camera Connectivity
```bash
./test_camera.sh
```

### View Logs
```bash
tail -f nvr.log
```

### Test RTSP Stream
```bash
ffplay "rtsp://username:password@192.168.0.76:554/ch0_1.264"
```

## Configuration

### Edit Camera Settings
```bash
nano config/config.yaml
```

### Edit Default Credentials
```bash
nano .env
```

## File Locations

- **Recordings**: `recordings/[camera-name]/`
- **Config**: `config/config.yaml`
- **Credentials**: `.env`
- **Logs**: `nvr.log`

## Documentation

- [README.md](README.md) - Full documentation
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
- [CAMERA_CONFIGS.md](CAMERA_CONFIGS.md) - Camera examples
- [PERFORMANCE.md](PERFORMANCE.md) - Performance tips

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `setup.sh` | Initial setup (one time) |
| `run.sh` | Main launcher (daily use) |
| `activate_venv.sh` | Activate virtual environment |
| `fix_onvif.sh` | Fix ONVIF installation |
| `test_camera.sh` | Test camera connectivity |
| `discover_cameras.py` | Discover ONVIF cameras |
| `test_discovery.py` | Debug discovery |
| `main.py` | Start NVR server |

## Common Workflows

### First Time Setup
```bash
./setup.sh
./run.sh fix-onvif    # If needed
./run.sh discover
./run.sh
```

### Daily Recording
```bash
./run.sh              # Start NVR
# Press Ctrl+C to stop
```

### Add New Camera
```bash
./run.sh discover     # Auto-discover
# or edit config/config.yaml manually
```

### Check Everything Works
```bash
./test_camera.sh      # Test camera
./run.sh test         # Test discovery
./run.sh discover     # Find cameras
./run.sh              # Start NVR
```
