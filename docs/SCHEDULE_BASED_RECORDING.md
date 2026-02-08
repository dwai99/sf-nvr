# Schedule-Based Recording Mode Configuration

**Date**: 2026-01-20
**Use Case**: Continuous recording during business hours, motion-only after hours

## Problem Statement

You want your bar's cameras to:
- **During business hours**: Record continuously (catch everything)
- **After hours**: Only record when motion is detected (save storage)

## Solution: Motion + Scheduled Mode

The **`motion_scheduled`** recording mode combines motion detection with time schedules, giving you the best of both worlds!

---

## 🎯 How It Works

### Motion + Scheduled Mode Logic

```
IF (current time is within schedule):
    Record continuously (24/7 coverage during business hours)
ELSE:
    Only record when motion detected (save storage after hours)
```

**Example Timeline (Business hours: 4 PM - 2 AM):**
```
00:00           16:00                        02:00           23:59
|░░░motion░░░░░|████████ continuous ████████|░░░motion░░░░░|
 After hours     Business hours (continuous)   After hours
 (motion only)                                 (motion only)
```

---

## 📝 Configuration for Your Bar

### Option 1: Continuous During Hours, Motion-Only After

This is likely what you want - full coverage when open, smart recording when closed.

**Edit `config/config.yaml`:**

```yaml
recording:
  # Set all cameras to use scheduled recording by default
  default_mode: motion_scheduled

  # Or configure per-camera (more granular control)
  camera_modes:
    "Alley": motion_scheduled
    "Patio": motion_scheduled
    "Patio Gate": motion_scheduled
    "Tool Room": motion_scheduled
    "Liquor Storage": motion_scheduled

recording_schedules:
  # Define your business hours
  bar_hours:
    start_hour: 16  # 4 PM
    end_hour: 2     # 2 AM (next day)
    days: [0, 1, 2, 3, 4, 5, 6]  # Every day (Mon=0, Sun=6)
```

**How it works:**
- **4 PM - 2 AM**: Continuous recording (business hours)
- **2 AM - 4 PM**: Motion-only recording (after hours)

### Option 2: Different Schedules for Different Days

If you have different hours on different days:

```yaml
recording_schedules:
  # Weekday hours (Mon-Thu: 4 PM - 12 AM)
  weekday_hours:
    start_hour: 16
    end_hour: 0
    days: [0, 1, 2, 3]  # Monday-Thursday

  # Weekend hours (Fri-Sat: 4 PM - 2 AM)
  weekend_hours:
    start_hour: 16
    end_hour: 2
    days: [4, 5]  # Friday-Saturday

  # Sunday (12 PM - 10 PM)
  sunday_hours:
    start_hour: 12
    end_hour: 22
    days: [6]  # Sunday only
```

Then configure cameras to use these schedules:

```yaml
recording:
  camera_modes:
    "Bar Area": motion_scheduled
```

**Note:** With multiple schedules, cameras will record continuously if ANY schedule is active.

### Option 3: Mixed Modes (Advanced)

Different cameras with different modes:

```yaml
recording:
  camera_modes:
    # Critical areas: Always record
    "Front Door": continuous
    "Cash Register": continuous

    # Activity areas: Scheduled + motion
    "Bar Area": motion_scheduled
    "Patio": motion_scheduled

    # Low-priority: Always motion-only
    "Tool Room": motion_only
    "Alley": motion_only
```

---

## 🔧 Step-by-Step Setup

### 1. Determine Your Business Hours

Figure out when you need **continuous** recording:
- Opening time: **_____ (hour)**
- Closing time: **_____ (hour)**
- Days of week: **_____ (0-6, where 0=Monday)**

### 2. Edit Configuration File

Open `config/config.yaml` and modify:

```yaml
recording:
  default_mode: motion_scheduled  # Apply to all cameras

recording_schedules:
  business_hours:
    start_hour: 16  # Replace with your opening hour (24-hour format)
    end_hour: 2     # Replace with your closing hour
    days: [0, 1, 2, 3, 4, 5, 6]  # All days, or specify specific days
```

### 3. Restart NVR

```bash
# Stop current NVR
# (Press Ctrl+C in terminal where it's running)

# Start NVR
python3 -m nvr.web.api
```

### 4. Verify Configuration

Check the logs on startup:
```
INFO - Recording mode for Alley: motion_scheduled
INFO - Recording mode for Patio: motion_scheduled
...
```

### 5. Test the System

**During business hours:**
- Open playback
- Timeline should show **solid green segments** (continuous recording)
- No gaps

**After business hours:**
- Timeline should show **sparse green segments** (only when motion)
- Gray gaps between segments = no motion, no recording

---

## 📊 Expected Storage Savings

### Before (Continuous 24/7)

```
Daily storage per camera: ~48 GB
5 cameras × 48 GB = 240 GB/day
7 days retention = 1.68 TB
```

### After (Motion-Scheduled)

**Assumptions:**
- Business hours: 10 hours/day continuous
- After hours: 14 hours/day motion-only (10% activity)

```
Business hours: 10 hours × 2 GB/hour = 20 GB
After hours: 14 hours × 0.2 GB/hour = 2.8 GB
Total per camera: ~23 GB/day

5 cameras × 23 GB = 115 GB/day
7 days retention = 805 GB

Savings: 52% reduction! (1.68 TB → 805 GB)
```

---

## 🎨 Timeline Visualization

### Continuous Mode (Old Way)
```
00:00                                                   23:59
|████████████████████████████████████████████████████████|
└─ 240 GB/day for 5 cameras
```

### Motion-Scheduled Mode (New Way)
```
00:00    04:00        16:00                02:00       23:59
|░░motion|░░░░░░░░░░░|█████ continuous ████|░░motion░░|
 After hrs  (saved)    Business hours       After hrs
 2.8GB                 20GB                 2.8GB
└─ 115 GB/day for 5 cameras (52% savings!)
```

---

## 🔍 Real-World Example

### Your Bar Setup

**Cameras:**
1. Alley
2. Patio
3. Patio Gate
4. Tool Room
5. Liquor Storage

**Hours:**
- Open: 4 PM (16:00)
- Close: 2 AM (02:00)
- Days: Every day

**Configuration:**

```yaml
recording:
  default_mode: motion_scheduled

recording_schedules:
  bar_hours:
    start_hour: 16
    end_hour: 2
    days: [0, 1, 2, 3, 4, 5, 6]
```

**What happens:**

**Tuesday 4 PM (Opening)**
- Alley camera: Switches to **continuous** mode
- Recording everything until 2 AM

**Wednesday 2 AM (Closing)**
- Alley camera: Switches to **motion-only** mode
- Only records when someone passes by

**Wednesday 3 AM (After hours)**
- Motion detected at Alley camera
- Records 45-second clip (5s before + 40s motion + 10s after)
- **Gap** in recording after motion ends

**Wednesday 4 PM (Re-opening)**
- All cameras switch back to **continuous** mode
- Cycle repeats

---

## 🚀 Advanced Configuration

### Per-Camera Schedules

If you want different cameras to have different schedules:

```yaml
recording:
  camera_modes:
    # Front cameras always continuous during bar hours
    "Front Door": motion_scheduled
    "Bar Area": motion_scheduled

    # Back cameras motion-only always (less important)
    "Alley": motion_only
    "Tool Room": motion_only

recording_schedules:
  bar_hours:
    start_hour: 16
    end_hour: 2
    days: [0, 1, 2, 3, 4, 5, 6]
```

### Multiple Schedule Periods

If you open for lunch AND dinner:

```yaml
recording_schedules:
  lunch_hours:
    start_hour: 11
    end_hour: 14
    days: [0, 1, 2, 3, 4, 5]  # Mon-Fri only

  dinner_hours:
    start_hour: 17
    end_hour: 23
    days: [0, 1, 2, 3, 4, 5, 6]  # Every day
```

Cameras will record continuously during **either** lunch OR dinner hours, motion-only otherwise.

### Overnight Hours (Handles Day Boundary)

If your schedule crosses midnight (like 4 PM - 2 AM), the system automatically handles the day boundary:

```yaml
bar_hours:
  start_hour: 16  # 4 PM
  end_hour: 2     # 2 AM next day
  days: [0, 1, 2, 3, 4, 5, 6]
```

**How it works:**
- Tuesday 4 PM: Starts continuous recording
- Wednesday 12 AM: Still recording (schedule spans midnight)
- Wednesday 2 AM: Switches to motion-only
- Wednesday 4 PM: Back to continuous

---

## 🎯 Playback with Scheduled Recording

### Auto-Skip Feature ✅

**NEW:** Gaps are now automatically skipped during playback!

When a video segment ends:
1. System finds the next available segment
2. Automatically loads and plays it
3. Console shows: `Gap skipped: 1847s. Loading next segment...`

**User Experience:**
- Press play → video plays continuously through all motion events
- Gaps are skipped seamlessly
- No manual intervention needed

### Timeline Shows Schedule

The timeline visually distinguishes recording periods:

```
Timeline for "Patio" camera (4 PM - 2 AM schedule):

00:00    04:00        16:00                02:00       23:59
|░██░░░░|░░░░░░░░░░░|████████████████████|░░██░░░░░░|
 Motion   No record   Continuous (schedule) Motion
 (gap)    (gap)       (solid green)         (gap)
```

**Legend:**
- 🟢 **Solid green**: Continuous recording (during schedule)
- 🟢 **Short green bars**: Motion events (outside schedule)
- ⚪ **Gray gaps**: No recording (no motion outside schedule)

---

## 📋 Troubleshooting

### Problem: Still recording continuously after hours

**Check:**
1. Verify `default_mode: motion_scheduled` in config
2. Check schedule times (use 24-hour format: 16 = 4 PM, 2 = 2 AM)
3. Restart NVR after config changes
4. Check logs for "Recording mode for [camera]: motion_scheduled"

### Problem: Not recording during business hours

**Check:**
1. Verify schedule `days` array includes correct days (0=Mon, 6=Sun)
2. Check `start_hour` and `end_hour` are correct
3. Verify time zone is correct (server time vs local time)
4. Check logs for "within schedule" messages

### Problem: Too many motion events after hours

**Adjust motion sensitivity:**
```yaml
motion_detection:
  enabled: true
  sensitivity: 30  # Higher = more sensitive (default 25)
```

Lower sensitivity (e.g., 20) = fewer false alarms

### Problem: Missing motion events after hours

**Adjust post-motion recording:**
```yaml
recording:
  camera_modes:
    "Patio": motion_scheduled

# In code (advanced):
# Increase post_motion_seconds to capture more after motion stops
```

---

## ✅ Quick Reference

### Day of Week Numbers
```
0 = Monday
1 = Tuesday
2 = Wednesday
3 = Thursday
4 = Friday
5 = Saturday
6 = Sunday
```

### Hour Format (24-hour)
```
12 AM = 0
1 AM = 1
...
12 PM = 12
1 PM = 13
2 PM = 14
3 PM = 15
4 PM = 16
...
11 PM = 23
```

### Common Schedules

**9-5 Office (Weekdays)**
```yaml
business_hours:
  start_hour: 9
  end_hour: 17
  days: [0, 1, 2, 3, 4]
```

**Retail Store (10 AM - 8 PM, Every Day)**
```yaml
store_hours:
  start_hour: 10
  end_hour: 20
  days: [0, 1, 2, 3, 4, 5, 6]
```

**Bar (4 PM - 2 AM, Every Day)**
```yaml
bar_hours:
  start_hour: 16
  end_hour: 2
  days: [0, 1, 2, 3, 4, 5, 6]
```

**Weekend Only (Fri-Sun)**
```yaml
weekend:
  start_hour: 12
  end_hour: 22
  days: [4, 5, 6]
```

---

## 🎉 Summary

**To configure continuous during the day, motion after hours:**

1. Edit `config/config.yaml`
2. Set `default_mode: motion_scheduled`
3. Define your business hours in `recording_schedules`
4. Restart NVR
5. Enjoy 50%+ storage savings!

**Benefits:**
- ✅ Full coverage during business hours
- ✅ Smart storage savings after hours
- ✅ Auto-skip gaps during playback
- ✅ Easy to configure and modify
- ✅ Visual timeline shows schedule periods

---

**Generated**: 2026-01-20
**Feature**: Schedule-Based Recording Mode
**Status**: ✅ Ready to Use
**Expected Savings**: 50-70% storage reduction

