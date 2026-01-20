# SF-NVR System Monitoring

## Overview

The NVR system now includes comprehensive monitoring tools to track system health, detect issues, and alert on critical problems.

## Quick Commands

### Check Current Status
```bash
./check_status.sh
```
Shows instant snapshot of:
- NVR process status (CPU, memory)
- Disk space usage
- Recordings storage size
- Recent errors
- System resources
- Monitor status

### View Live Monitoring
```bash
./monitor_live.sh
```
Shows real-time updates every 30 seconds with alerts.

### View Monitoring Logs
```bash
# View all monitoring logs
tail -f system_monitor.log

# View only alerts
tail -f system_alerts.log
```

## Monitoring Components

### 1. Background Monitor (`watch_system.sh`)
**Status:** Running automatically in background

**Monitors:**
- NVR process status (alerts if stopped)
- Disk space (alerts at 85% and 95%)
- Recent errors in logs
- Memory usage

**Check Interval:** Every 30 seconds

**Logs:**
- `system_monitor.log` - All monitoring events
- `system_alerts.log` - Only critical alerts

**Control:**
```bash
# Check if running
ps aux | grep watch_system.sh

# Stop monitoring
pkill -f watch_system.sh

# Restart monitoring
./watch_system.sh &
```

### 2. Advanced Monitor (`monitor_system.py`)
**Status:** Available for detailed analysis

A Python-based monitor with rich dashboard display showing:
- NVR process details
- Active camera streams
- Disk space with color-coded warnings
- System CPU/memory usage
- Recent errors (filtered to show only critical)
- Recordings storage size

**Usage:**
```bash
# Run in foreground (displays dashboard)
python3 monitor_system.py

# Run in background
python3 monitor_system.py > monitor_output.log 2>&1 &
```

**Features:**
- Color-coded status indicators
- Real-time dashboard updates
- Detailed error analysis
- Camera stream verification
- Configurable thresholds

## Alert Thresholds

### Disk Space
- **WARNING:** 85% used
- **CRITICAL:** 95% used

### Memory
- **WARNING:** 90% used

### CPU
- **WARNING:** 95% sustained usage

## Log Files

| File | Purpose |
|------|---------|
| `system_monitor.log` | All monitoring events and status updates |
| `system_alerts.log` | Critical alerts only (disk space, process down, etc.) |
| `nvr.log` | NVR application logs (checked for errors) |

## What Gets Monitored

### NVR Process Health
- ✅ Process running status
- ✅ CPU usage
- ✅ Memory consumption
- ✅ Process ID

### Camera Streams
- ✅ Active streaming status
- ✅ Number of cameras streaming
- ✅ Recent stream activity

### Storage
- ✅ Total disk space
- ✅ Free disk space
- ✅ Recordings directory size
- ✅ Usage percentage

### System Resources
- ✅ Overall CPU usage
- ✅ Memory usage
- ✅ System load

### Error Detection
- ✅ Recent errors in logs
- ✅ Critical errors
- ✅ Filters out known non-critical errors (ONVIF WSDL)

## Alerts

Alerts are logged when:

1. **NVR Process Stops**
   - Alert: "NVR process is NOT running!"
   - Action: Check `nvr.log` for crash reason, restart manually

2. **Disk Space Critical (95%+)**
   - Alert: "Disk space CRITICAL: XX% used"
   - Action: Delete old recordings or add more storage

3. **Disk Space Warning (85%+)**
   - Alert: "Disk space WARNING: XX% used"
   - Action: Plan to free space soon

4. **Memory High (90%+)**
   - Alert: "Memory usage high: XX%"
   - Action: Consider restarting system if sustained

5. **Errors in Logs**
   - Alert: "Found X error(s) in last 50 log lines"
   - Action: Check `nvr.log` for details

## Troubleshooting

### Monitor Not Running
```bash
# Check status
ps aux | grep watch_system.sh

# If not running, start it
./watch_system.sh &

# Verify it started
tail system_monitor.log
```

### Too Many Alerts
Edit `watch_system.sh` and adjust:
- `CHECK_INTERVAL` - Increase to check less frequently
- Alert thresholds (85%, 95%, etc.)

### Need More Details
Run the Python monitor for detailed analysis:
```bash
python3 monitor_system.py
```

## Integration with System

### Auto-start on Boot
Add to crontab:
```bash
crontab -e
```

Add line:
```
@reboot cd /path/to/sf-nvr && ./watch_system.sh &
```

### Email Alerts (Future Enhancement)
The monitoring system can be extended to send email/SMS alerts using:
- SendGrid for email
- Twilio for SMS
- Webhooks for custom integrations

## Files

| File | Description |
|------|-------------|
| `watch_system.sh` | Background monitoring daemon |
| `check_status.sh` | Quick status check script |
| `monitor_live.sh` | Live monitoring display |
| `monitor_system.py` | Advanced Python monitor |
| `system_monitor.log` | Monitoring events log |
| `system_alerts.log` | Critical alerts log |

## Tips

1. **Run status check regularly:**
   ```bash
   watch -n 10 ./check_status.sh  # Updates every 10 seconds
   ```

2. **Monitor during recordings:**
   ```bash
   ./monitor_live.sh
   ```

3. **Check for issues after restart:**
   ```bash
   ./check_status.sh
   tail -n 50 system_alerts.log
   ```

4. **Create alert for your phone:**
   Set up a cron job to send you status via email/SMS when disk is high.

## Next Steps

The monitoring system is ready for Phase 1 enhancements:
- [ ] Web dashboard for monitoring (see Phase 1, Task 1)
- [ ] Email/SMS alerts integration (see Phase 2, Task 5)
- [ ] Historical metrics and graphing
- [ ] Storage prediction and warnings
