# Setting Up AI Person & Vehicle Detection

AI detection is currently **disabled by default** due to model download complexities. Follow these steps to enable it.

## Quick Start

```bash
# Option 1: Try automatic download (may fail due to changing URLs)
./download_ai_models.sh

# Option 2: Manual download (recommended)
# See "Manual Download" section below
```

## Manual Download (Recommended)

The MobileNet-SSD model files need to be placed in the `models/` directory.

### Step 1: Create models directory
```bash
mkdir -p models
cd models
```

### Step 2: Download model files

**Option A - Using wget:**
```bash
# Download config file
wget https://raw.githubusercontent.com/opencv/opencv_extra/master/testdata/dnn/MobileNetSSD_deploy.prototxt

# Download weights (23MB)
wget https://github.com/chuanqi305/MobileNet-SSD/raw/master/MobileNetSSD_deploy.caffemodel
```

**Option B - Using curl:**
```bash
# Download config file
curl -L -o MobileNetSSD_deploy.prototxt \
  https://raw.githubusercontent.com/opencv/opencv_extra/master/testdata/dnn/MobileNetSSD_deploy.prototxt

# Download weights (23MB)
curl -L -o MobileNetSSD_deploy.caffemodel \
  https://github.com/chuanqi305/MobileNet-SSD/raw/master/MobileNetSSD_deploy.caffemodel
```

**Option C - Manual browser download:**

1. Download config file:
   - URL: https://github.com/opencv/opencv_extra/blob/master/testdata/dnn/MobileNetSSD_deploy.prototxt
   - Save as: `models/MobileNetSSD_deploy.prototxt`

2. Download model weights:
   - URL: https://github.com/chuanqi305/MobileNet-SSD/blob/master/MobileNetSSD_deploy.caffemodel
   - Save as: `models/MobileNetSSD_deploy.caffemodel`

### Step 3: Verify files

```bash
ls -lh models/

# You should see:
# MobileNetSSD_deploy.prototxt (~29KB)
# MobileNetSSD_deploy.caffemodel (~23MB)
```

Expected file sizes:
- `MobileNetSSD_deploy.prototxt`: ~29KB (should be > 1KB)
- `MobileNetSSD_deploy.caffemodel`: ~23MB

### Step 4: Enable AI detection

Edit `config/config.yaml`:

```yaml
ai_detection:
  enabled: true  # Change from false to true
  confidence_threshold: 0.5
  frame_check_interval: 30
  detect_person: true
  detect_vehicle: true
```

### Step 5: Restart NVR

```bash
# Stop if running (Ctrl+C)

# Start again
./start.sh
```

You should see in the logs:
```
INFO - AI detection enabled (person/vehicle recognition)
INFO - Model loaded successfully
INFO - AI monitoring started for person/vehicle detection
```

## Troubleshooting

### Model download fails

**Problem**: 404 errors or small files (14 bytes)

**Solution**: Use manual download (Option C above) - download files directly from browser

### "Model load error"

**Problem**: `Error loading model: Could not open`

**Solutions**:
1. Verify files exist: `ls -lh models/`
2. Check file sizes (prototxt ~29KB, caffemodel ~23MB)
3. Re-download if files are corrupted

### "AttributeError: module 'cv2.dnn' has no attribute 'readNetFromCaffe'"

**Problem**: OpenCV not compiled with DNN support

**Solution**:
```bash
# Reinstall OpenCV with DNN support
pip uninstall opencv-python
pip install opencv-contrib-python
```

### High CPU usage

**Problem**: System slow when AI detection running

**Solutions**:
1. Increase `frame_check_interval` to 60 or 90
2. Disable AI on some cameras
3. Use fewer cameras

### No detections logged

**Problem**: AI running but no person/vehicle events

**Check**:
1. Verify AI is enabled in config
2. Check logs for "AI: PERSON detected" or "AI: VEHICLE detected"
3. Lower `confidence_threshold` to 0.3 temporarily
4. Ensure cameras have person/vehicle traffic

## Alternative: Using Without AI

The NVR works perfectly without AI detection:

1. Leave `ai_detection.enabled: false` in config
2. Use motion detection only (already enabled)
3. All footage is still recorded continuously
4. Review using playback with motion event markers

**You still get**:
- ✅ 24/7 continuous recording
- ✅ Motion detection events
- ✅ Full playback system
- ✅ Law enforcement export

**You won't have**:
- ❌ Person/vehicle specific detection
- ❌ Smart filtering of events

## Testing AI Detection

Once enabled, test it:

```bash
# Start NVR
./start.sh

# Watch logs for AI activity
# Walk in front of a camera
# You should see:
# "AI: PERSON detected on [camera name]"

# Check database
sqlite3 recordings/playback.db "SELECT * FROM motion_events WHERE event_type LIKE 'ai_%' ORDER BY event_time DESC LIMIT 5;"
```

## Performance Impact

With AI detection enabled (6 cameras):

- **CPU Usage**: +10-15% (from ~10% to ~25%)
- **Detection Latency**: ~30-50ms per frame
- **Frame Check Rate**: Every 30 frames (~1/sec at 30fps)

## Support

If you continue to have issues:

1. Disable AI detection (`enabled: false`)
2. Use motion detection only
3. File an issue with error logs

The system is fully functional without AI - it's an enhancement, not a requirement.
