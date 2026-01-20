# Performance Optimizations

## Discovery Speed Improvements

### What Changed

**Before:**
- Scanned 254 IPs × 3 ports = 762 combinations
- Used blocking sockets (slow)
- 0.5s timeout × 762 = ~6 minutes worst case
- All ports scanned regardless of results

**After:**
- Uses **true async I/O** with asyncio.open_connection
- Scans all 254 IPs in **parallel** (not sequential)
- Reduced timeout to 0.2s (200ms)
- **Smart scanning**: Port 80 first, then others only if needed
- Expected completion: **5-15 seconds** for most networks

### Expected Performance

**Empty subnet (no cameras):**
- Port 80 scan: ~5 seconds (254 IPs × 0.2s timeout, all parallel)
- Additional ports: ~10 seconds if needed
- Total: **5-15 seconds**

**With cameras:**
- Port scan: ~5 seconds
- ONVIF testing: 2s per camera (done sequentially for reliability)
- With 3 cameras: **~11 seconds total**

## How It Works Now

### Phase 1: Ultra-Fast Port Scan (5 seconds)

```python
# Launch 254 connection attempts simultaneously
# Each has 200ms timeout
# asyncio handles all concurrently
await asyncio.gather(*[check_port(ip, 80) for ip in all_ips])
```

All 254 IPs checked in parallel = **time of slowest response** (not sum of all)

### Phase 1b: Smart Additional Scanning (optional)

Only runs if fewer than 5 devices found on port 80:
```python
if len(found) < 5:
    # Check ports 8080 and 8000
    # Another ~10 seconds
```

### Phase 2: ONVIF Verification (2s per camera)

Tests each responsive host:
```python
for ip, port in responsive_hosts:
    # Try ONVIF connection (2s timeout)
    # Done sequentially to avoid overwhelming cameras
```

## Current Optimizations

1. **Async I/O**: Native asyncio instead of blocking sockets
2. **Massive Parallelism**: All IPs checked simultaneously
3. **Short Timeouts**: 200ms for port check, 2s for ONVIF
4. **Smart Scanning**: Port 80 first (most common)
5. **Early Exit**: Skip additional ports if cameras found

## Configuration Options

### For Even Faster Discovery

Edit `config/config.yaml`:

```yaml
onvif:
  discovery_timeout: 1  # Reduce to 1 second (risky on slow networks)
```

### For More Thorough Discovery

```yaml
onvif:
  discovery_timeout: 3  # Increase if cameras are slow to respond
```

## Benchmarks

Expected times on typical home network:

| Scenario | Time |
|----------|------|
| No cameras found | 5-7 seconds |
| 1-2 cameras on port 80 | 9-11 seconds |
| 3-5 cameras on port 80 | 11-17 seconds |
| Cameras on non-standard ports | 15-25 seconds |

## Troubleshooting Slow Discovery

### Still taking 30+ seconds?

**Check 1: Network congestion**
```bash
# Test network speed
ping -c 10 192.168.1.1
# Should be < 5ms on local network
```

**Check 2: Firewall blocking**
- Some firewalls delay responses instead of dropping packets
- Check firewall logs
- Try temporarily disabling firewall

**Check 3: Python version**
- Python 3.8+ required for optimal asyncio performance
- Check: `python3 --version`

**Check 4: Too many background processes**
```bash
# Check system load
top      # macOS/Linux
```

### Optimization Tips

1. **Know your camera IPs?** Use manual config instead:
   ```yaml
   cameras:
     - name: "Camera 1"
       rtsp_url: "rtsp://admin:pass@192.168.1.100:554/stream1"
   ```

2. **Smaller subnet**: If cameras are 192.168.1.100-110, modify discovery code

3. **Run during off-peak**: Less network congestion = faster scans

## Technical Details

### Why Asyncio Is Faster

**Blocking sockets (old way):**
```python
# Check each IP one at a time
for ip in ips:
    sock.connect(ip)  # Wait up to 0.5s
    # Total: 254 × 0.5s = 127 seconds
```

**Async sockets (new way):**
```python
# Check all IPs simultaneously
tasks = [connect(ip) for ip in ips]
await asyncio.gather(*tasks)
# Total: ~0.5s (all parallel)
```

### Network Capacity

Local networks can easily handle:
- 254 simultaneous connections
- Each is tiny (just SYN packet)
- Total bandwidth: < 100KB
- No risk of overwhelming network

### OS Limits

Some systems limit concurrent connections:

**macOS/Linux:**
```bash
ulimit -n  # Check max open files
# Should be > 1024
```

**Windows:**
- Usually no issues
- Default limits are high enough

## Monitoring Performance

### Add timing logs

Edit `nvr/core/onvif_discovery.py`:

```python
import time

# At start of _scan_ip_range:
start = time.time()

# At end:
elapsed = time.time() - start
logger.info(f"Total scan time: {elapsed:.1f} seconds")
```

### Debug mode

For detailed timing:
```bash
# In main.py, set:
logging.basicConfig(level=logging.DEBUG)
```

You'll see:
- Each port check attempt
- Exact timing for each phase
- Connection errors and timeouts
