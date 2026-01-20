# Segment Timing Update

## Summary
Updated recording segments to align with clock intervals instead of recording start time.

## Changes Made

### 1. Clock-Aligned Segments
**Before:** Segments started 5 minutes after the stream connected (unpredictable filenames)
**After:** Segments align to clock boundaries: 00:00, 00:05, 00:10, 00:15, etc.

### 2. Consistent Filenames
**Example:**
- Stream starts at 14:32:17
- Old behavior: First file = `20260119_143217.mp4`, Second file = `20260119_143717.mp4`
- New behavior: First file = `20260119_143000.mp4`, Second file = `20260119_143500.mp4`

### 3. Benefits
- **Predictable filenames** across system restarts
- **Easier to find** recordings at specific times
- **Better organization** - all cameras align to same time boundaries
- **No gaps** when restarting - new recording continues from next boundary

## Implementation Details

### Segment Boundary Calculation
```python
def _get_next_segment_boundary(self) -> datetime:
    """Calculate next 5-minute boundary (00:00, 00:05, 00:10, etc.)"""
    now = datetime.now()
    segment_minutes = self.segment_duration // 60  # 300 seconds = 5 minutes
    minutes_since_midnight = now.hour * 60 + now.minute
    next_boundary_minutes = ((minutes_since_midnight // segment_minutes) + 1) * segment_minutes
    # Convert back to datetime...
```

### Recording Loop
Instead of counting frames to decide when to start new segments, the recorder now:
1. Calculates the next clock boundary when starting
2. Checks the current time on each frame
3. Starts a new segment when the boundary is reached

## Example Timeline

**With 5-minute segments starting at 14:32:17:**

| Time | Event |
|------|-------|
| 14:32:17 | Stream starts |
| 14:32:17 | Creates `20260119_143000.mp4` (aligned to 14:30) |
| 14:35:00 | Closes current segment, starts `20260119_143500.mp4` |
| 14:40:00 | Closes current segment, starts `20260119_144000.mp4` |
| 14:45:00 | Closes current segment, starts `20260119_144500.mp4` |

All files align perfectly to 5-minute boundaries regardless of when recording actually started.

## Configuration

Segment duration is configured in `config/config.yaml`:
```yaml
recording:
  segment_duration: 300  # 5 minutes (in seconds)
```

**Recommended:** Keep at 300 seconds (5 minutes) for optimal balance of:
- Fast playback seeking
- Manageable file counts
- Minimal data loss on crashes
