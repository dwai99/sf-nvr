# Camera Configuration Examples

## Night Owl Cameras

### Auto-Discovery
Night Owl cameras use **port 8089** for ONVIF (non-standard). The discovery tool now includes this port automatically.

### Manual Configuration

```yaml
cameras:
  - name: "Night Owl Front"
    rtsp_url: "rtsp://admin:password@192.168.0.76:554/ch0_0.264"  # Main stream (2560x1440)
    # OR for lower bandwidth:
    # rtsp_url: "rtsp://admin:password@192.168.0.76:554/ch0_1.264"  # Sub stream (720x480)
    onvif_host: "192.168.0.76"
    onvif_port: 8089  # Important: Night Owl uses 8089, not 80
    username: "admin"
    password: "your_password"
    enabled: true
    device_info:
      manufacturer: "Night Owl SP"
      model: "WCM-FWIP4L-BS-U-V2"
```

### Stream Options

Night Owl cameras typically provide two streams:

**Main Stream (High Quality)**
- URL: `rtsp://IP:554/ch0_0.264`
- Resolution: 2560x1440 (or camera max)
- Use for: Recording, high-quality playback
- Bandwidth: ~4-8 Mbps

**Sub Stream (Low Quality)**
- URL: `rtsp://IP:554/ch0_1.264`
- Resolution: 720x480
- Use for: Live monitoring, motion detection, multiple cameras
- Bandwidth: ~0.5-1 Mbps

### Recommended Settings

For Night Owl cameras:

```yaml
recording:
  video_codec: "h264"  # Night Owl streams are H.264
  container_format: "mp4"

motion_detection:
  enabled: true
  sensitivity: 20  # Night Owl cameras can be sensitive
  min_area: 800    # Adjust based on camera placement
```

## Hikvision Cameras

### ONVIF Port
Port 80 (standard)

### RTSP URLs

**Main Stream:**
```
rtsp://username:password@IP:554/Streaming/Channels/101
```

**Sub Stream:**
```
rtsp://username:password@IP:554/Streaming/Channels/102
```

### Configuration Example

```yaml
cameras:
  - name: "Hikvision Front Door"
    rtsp_url: "rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101"
    onvif_host: "192.168.1.100"
    onvif_port: 80
    username: "admin"
    password: "your_password"
    enabled: true
```

## Dahua Cameras

### ONVIF Port
Port 80 (standard)

### RTSP URLs

**Main Stream:**
```
rtsp://username:password@IP:554/cam/realmonitor?channel=1&subtype=0
```

**Sub Stream:**
```
rtsp://username:password@IP:554/cam/realmonitor?channel=1&subtype=1
```

### Configuration Example

```yaml
cameras:
  - name: "Dahua Backyard"
    rtsp_url: "rtsp://admin:password@192.168.1.101:554/cam/realmonitor?channel=1&subtype=0"
    onvif_host: "192.168.1.101"
    onvif_port: 80
    username: "admin"
    password: "your_password"
    enabled: true
```

## Reolink Cameras

### ONVIF Port
Port 8000 (non-standard)

### RTSP URLs

**Main Stream:**
```
rtsp://username:password@IP:554/h264Preview_01_main
```

**Sub Stream:**
```
rtsp://username:password@IP:554/h264Preview_01_sub
```

### Configuration Example

```yaml
cameras:
  - name: "Reolink Driveway"
    rtsp_url: "rtsp://admin:password@192.168.1.102:554/h264Preview_01_main"
    onvif_host: "192.168.1.102"
    onvif_port: 8000  # Reolink uses 8000
    username: "admin"
    password: "your_password"
    enabled: true
```

## Amcrest Cameras

### ONVIF Port
Port 80 (standard)

### RTSP URLs

**Main Stream:**
```
rtsp://username:password@IP:554/cam/realmonitor?channel=1&subtype=0
```

**Sub Stream:**
```
rtsp://username:password@IP:554/cam/realmonitor?channel=1&subtype=1
```

### Configuration Example

```yaml
cameras:
  - name: "Amcrest Side"
    rtsp_url: "rtsp://admin:password@192.168.1.103:554/cam/realmonitor?channel=1&subtype=0"
    onvif_host: "192.168.1.103"
    onvif_port: 80
    username: "admin"
    password: "your_password"
    enabled: true
```

## Generic ONVIF Cameras

### Finding RTSP URL

1. **Check manufacturer documentation**
2. **Use ONVIF Device Manager** (Windows tool)
3. **Try common patterns:**
   - `rtsp://IP:554/stream1`
   - `rtsp://IP:554/live`
   - `rtsp://IP:554/main`
   - `rtsp://IP:554/ch0`
   - `rtsp://IP:554/0`

### Testing RTSP URL

```bash
# Test with ffplay
ffplay "rtsp://username:password@IP:554/stream1"

# Or with VLC
# File > Open Network Stream
# Enter RTSP URL
```

## Multi-Camera Setup Example

```yaml
cameras:
  # Night Owl cameras
  - name: "Front Door"
    rtsp_url: "rtsp://admin:pass@192.168.0.76:554/ch0_0.264"
    onvif_host: "192.168.0.76"
    onvif_port: 8089
    username: "admin"
    password: "your_password"
    enabled: true

  - name: "Backyard"
    rtsp_url: "rtsp://admin:pass@192.168.0.77:554/ch0_0.264"
    onvif_host: "192.168.0.77"
    onvif_port: 8089
    username: "admin"
    password: "your_password"
    enabled: true

  # Hikvision camera
  - name: "Garage"
    rtsp_url: "rtsp://admin:hik@192.168.0.100:554/Streaming/Channels/101"
    onvif_host: "192.168.0.100"
    onvif_port: 80
    username: "admin"
    password: "hik_password"
    enabled: true
```

## Performance Optimization

### Use Sub-Streams When Possible

For cameras where you don't need high resolution:

```yaml
cameras:
  - name: "Low Priority Camera"
    rtsp_url: "rtsp://admin:pass@IP:554/ch0_1.264"  # Sub stream
    # Instead of ch0_0.264 (main stream)
```

Benefits:
- Lower CPU usage
- Lower bandwidth
- Lower storage requirements
- Can handle more cameras simultaneously

### Main Stream vs Sub Stream Guidelines

**Use Main Stream for:**
- Primary security cameras (entrances, high-value areas)
- Cameras where you need to identify faces/license plates
- Final recordings that may be used as evidence

**Use Sub Stream for:**
- General monitoring
- Motion detection only
- Live viewing dashboard
- Cameras covering low-priority areas

## Special Characters in Passwords

If your password contains special characters, URL-encode them:

```
@ → %40
# → %23
& → %26
? → %3F
= → %3D
% → %25
```

Example:
```yaml
# Password: "admin@123#"
rtsp_url: "rtsp://admin:admin%40123%23@IP:554/stream"
```

## Troubleshooting Camera Connections

### Camera not discovered

1. **Check ONVIF port:**
   ```bash
   # Try common ports
   curl -v http://IP:80/onvif/device_service
   curl -v http://IP:8000/onvif/device_service
   curl -v http://IP:8080/onvif/device_service
   curl -v http://IP:8089/onvif/device_service  # Night Owl
   ```

2. **Enable ONVIF in camera settings:**
   - Log into camera web interface
   - Look for Network > Integration or Network > ONVIF
   - Enable ONVIF
   - Note the port number

### RTSP stream not working

1. **Test with ffplay:**
   ```bash
   ffplay -rtsp_transport tcp "rtsp://user:pass@IP:554/stream"
   ```

2. **Try TCP transport:**
   ```yaml
   # Some cameras require TCP instead of UDP
   # This is handled automatically by the NVR
   ```

3. **Check stream path:**
   - Consult camera manual
   - Try common paths listed above
   - Use ONVIF Device Manager to find exact URL

### Connection timeout

1. **Reduce timeout** in camera settings
2. **Check network latency:**
   ```bash
   ping -c 10 CAMERA_IP
   # Should be < 10ms
   ```
3. **Ensure camera has enough connections available** (close other viewers)
