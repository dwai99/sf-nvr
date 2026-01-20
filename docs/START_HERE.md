# SF-NVR - Start Here

## ✅ Installation Complete!

Your NVR is ready. You have **6 Night Owl cameras** discovered on your network.

## 🚀 Quick Start (3 commands)

```bash
# 1. Discover cameras and save to config
./discover.sh

# 2. Start the NVR
./start.sh

# 3. Open browser
open http://localhost:8080
```

That's it!

## 📋 What Each Script Does

| Script | Purpose |
|--------|---------|
| `./discover.sh` | Find cameras and save to config |
| `./start.sh` | Start NVR web server |
| `./install.sh` | Re-run installation (if needed) |

## 🎥 Your Cameras

Found 6 Night Owl cameras:
- 192.168.0.12:8089 (WCM-FWIP4L-BS-U-V2)
- 192.168.0.52:8089 (WNIP-8LTA-BS-U)
- 192.168.0.76:8089 (WCM-FWIP4L-BS-U-V2)
- 192.168.0.118:8089
- 192.168.0.144:8089
- 192.168.0.235:8089

All on **port 8089** (Night Owl specific).

## ⚙️ Configuration

Edit `config/config.yaml`:
```yaml
recording:
  retention_days: 7      # Keep recordings for 7 days
  segment_duration: 300  # 5 min per file

motion_detection:
  enabled: true
  sensitivity: 25
```

Edit `.env` for camera credentials:
```
DEFAULT_CAMERA_USERNAME=admin
DEFAULT_CAMERA_PASSWORD=your_password
```

## 🔧 Troubleshooting

**"Module not found"**
```bash
source venv/bin/activate
python3 discover.py
```

**Can't find cameras**
```bash
# Check camera is online
ping 192.168.0.76

# Test RTSP
ffplay "rtsp://admin:password@192.168.0.76:554/ch0_1.264"
```

## 📚 More Documentation

- [README.md](README.md) - Full documentation
- [CAMERA_CONFIGS.md](CAMERA_CONFIGS.md) - Camera examples
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues

## 💡 Tips

**Use sub-streams for better performance:**
- Main: `rtsp://IP:554/ch0_0.264` (2560x1440)
- Sub: `rtsp://IP:554/ch0_1.264` (720x480) ← Recommended for 6 cameras

**Web interface:**
- Live view: http://localhost:8080
- Start/stop individual cameras
- View recordings
- Motion detection indicators
