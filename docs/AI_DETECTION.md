# AI Person & Vehicle Detection

SF-NVR now includes intelligent AI-based detection that recognizes **people** and **vehicles** while ignoring other motion like trees, animals, or shadows.

## How It Works

### Continuous Recording + Smart Detection

Your NVR system uses a **dual-layer approach** for maximum reliability:

1. **Layer 1: Continuous 24/7 Recording** (Always On)
   - All cameras record everything continuously
   - Nothing is ever missed
   - Full backup if AI detection has issues

2. **Layer 2: AI Smart Detection** (Person & Vehicle Only)
   - Analyzes frames for people and vehicles
   - Creates timeline markers for quick review
   - Helps you find incidents fast

**You get the best of both worlds**: Full coverage + Smart alerts

## Features

### What Gets Detected

✅ **People** - Customers, staff, intruders
✅ **Vehicles** - Cars, motorcycles, bicycles, buses

❌ **Ignored** - Trees moving, animals, shadows, lighting changes

### Detection Events

Events are logged to the database with types:
- `ai_person` - Person detected
- `ai_vehicle` - Vehicle detected
- `motion` - General motion detection (fallback)

## Configuration

Edit [config/config.yaml](config/config.yaml):

```yaml
ai_detection:
  enabled: true                    # Enable/disable AI detection
  confidence_threshold: 0.5        # Detection confidence (0.0-1.0)
  frame_check_interval: 30         # Check every N frames (higher = less CPU)
  detect_person: true              # Detect people
  detect_vehicle: true             # Detect vehicles
```

### Performance Tuning

**frame_check_interval** controls CPU usage:
- `10` = Check every 10 frames (~3x/second at 30fps) - More detections, higher CPU
- `30` = Check every 30 frames (~1x/second at 30fps) - **Recommended** - Balanced
- `60` = Check every 60 frames (~0.5x/second at 30fps) - Lower CPU, might miss quick events

**confidence_threshold** controls accuracy:
- `0.3` = More detections, more false positives
- `0.5` = **Recommended** - Good balance
- `0.7` = Fewer detections, very high confidence only

## How Detection Works

### Technology

- **Model**: MobileNet-SSD (optimized for real-time on CPU)
- **Framework**: OpenCV DNN module
- **Classes**: 20 object types (we only use person + vehicles)
- **Performance**: ~30-50ms per frame on modern CPU
- **Auto-download**: Model files download automatically on first run (~23MB)

### Detection Process

1. Frame is captured from camera
2. Every Nth frame (based on `frame_check_interval`) is analyzed
3. AI model detects objects and classifies them
4. Only person/vehicle detections are logged
5. Events are saved to database with timestamps
6. All frames continue to be recorded to video

### Event Logging

When a person or vehicle is detected:

1. **Event Start**: First detection creates event with timestamp
2. **Event Active**: Continues counting frames while object is present
3. **Event End**: No longer detected - saves to database with duration

Example database entry:
```
camera_name: "Front Door"
event_type: "ai_person"
event_time: 2025-01-15 14:23:45
duration_seconds: 12.5
frame_count: 375
confidence/intensity: 1.0 (person) or 0.5 (vehicle)
```

## Playback with AI Events

In the playback interface:

1. AI detection events appear as timeline markers
2. Click "ai_person" or "ai_vehicle" to filter
3. Motion events (non-AI) still shown for backup
4. Export includes all events regardless of type

## Use Cases for Bars

### Incident Investigation
**Scenario**: Fight breaks out at 2 AM

**Without AI**: Scan through hours of footage
**With AI**: Jump to person detection events around 2 AM

### Staff Monitoring
**Scenario**: Check closing procedures

**Without AI**: Watch entire close from 2 AM - 3 AM
**With AI**: See when people entered/exited bar area

### Parking Lot Security
**Scenario**: Vandalism in parking lot

**Without AI**: Review all motion (wind, animals, etc.)
**With AI**: Only see when vehicles or people were present

### Law Enforcement Export
When police need footage:

1. Navigate to incident time
2. See AI markers showing person/vehicle activity
3. Export exact timeframe with all cameras
4. Provide to law enforcement on USB drive

## Technical Details

### Model Files

Located in `models/` directory:
- `MobileNetSSD_deploy.prototxt` - Model configuration (1KB)
- `MobileNetSSD_deploy.caffemodel` - Model weights (23MB)

Auto-downloaded from: https://github.com/chuanqi305/MobileNet-SSD

### Database Schema

AI events stored in `motion_events` table:

```sql
CREATE TABLE motion_events (
    id INTEGER PRIMARY KEY,
    camera_name TEXT NOT NULL,
    event_time TIMESTAMP NOT NULL,
    duration_seconds REAL,
    frame_count INTEGER,
    intensity REAL,              -- 1.0 for person, 0.5 for vehicle
    event_type TEXT,             -- 'ai_person', 'ai_vehicle', or 'motion'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### CPU Usage

On a typical system with 6 cameras:

**Without AI** (~10% CPU):
- Motion detection only (simple background subtraction)
- Checking every frame

**With AI** (~20-30% CPU):
- Motion detection (every frame)
- AI detection (every 30th frame)
- Still very efficient for 24/7 operation

**Tips to reduce CPU**:
- Increase `frame_check_interval` to 60 or 90
- Disable motion detection, use AI only
- Use sub-streams (lower resolution) for detection

## Troubleshooting

### Model Download Fails

```bash
# Manual download
cd models/
wget https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/MobileNetSSD_deploy.prototxt
wget https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/MobileNetSSD_deploy.caffemodel
```

### High CPU Usage

1. Increase `frame_check_interval` in config (try 60 or 90)
2. Reduce number of cameras with AI enabled
3. Use lower resolution streams if available

### False Detections

- Increase `confidence_threshold` to 0.6 or 0.7
- Check camera angle - aim at areas of interest
- Shadows and reflections can sometimes trigger person detection

### Missing Detections

- Decrease `confidence_threshold` to 0.3 or 0.4
- Decrease `frame_check_interval` to check more often
- Ensure camera has good lighting
- Check if object is fully visible in frame

### No AI Events in Database

1. Check config: `ai_detection.enabled: true`
2. Check logs for AI detection startup
3. Verify model files downloaded to `models/` directory
4. Test on camera with known person/vehicle traffic

## Logs

Check logs for AI detection activity:

```bash
# Start NVR and watch logs
./start.sh

# Look for:
# "AI detection enabled (person/vehicle recognition)"
# "AI monitoring started for person/vehicle detection"
# "AI: PERSON detected on [camera name]"
# "AI: VEHICLE detected on [camera name]"
```

## Future Enhancements

Planned improvements:

- [ ] Facial recognition for known persons
- [ ] License plate recognition
- [ ] Crowd counting
- [ ] Loitering detection
- [ ] Line crossing alerts
- [ ] Motion zones (ignore certain areas)
- [ ] Real-time push notifications
- [ ] GPU acceleration (NVIDIA, Intel QuickSync)
- [ ] Custom AI models training

## Performance Comparison

### Detection Accuracy

**Motion Detection** (Background subtraction):
- Pros: Very fast, low CPU
- Cons: Detects everything (trees, shadows, animals)
- Use case: Backup detection layer

**AI Detection** (MobileNet-SSD):
- Pros: Only people/vehicles, fewer false alerts
- Cons: Slightly higher CPU, may miss small/distant objects
- Use case: Primary smart detection

### Best Practice: Use Both

Current configuration uses both:
1. **Continuous recording** - Everything is saved
2. **Motion detection** - Fast, catches all movement
3. **AI detection** - Smart filtering for people/vehicles

Review workflow:
1. Check AI person/vehicle events first (targeted)
2. Fall back to motion events if needed (comprehensive)
3. Always have full 24/7 recording as ultimate backup

## Support

For issues or questions:
- Check logs for error messages
- Review [COMMERCIAL_ENHANCEMENTS.md](COMMERCIAL_ENHANCEMENTS.md) for planned features
- File issues at: (your repo URL)

## Credits

- **Model**: MobileNet-SSD by chuanqi305
- **Framework**: OpenCV DNN module
- **Training Data**: COCO dataset (Common Objects in Context)
