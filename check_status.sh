#!/bin/bash
# Quick status check for SF-NVR system

echo "================================================================================"
echo "                         SF-NVR Quick Status Check"
echo "                        $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================================"
echo

# Check NVR process
echo "📹 NVR Process:"
if pgrep -f "main.py" > /dev/null; then
    pid=$(pgrep -f "main.py")
    echo "   ✓ Running (PID: $pid)"
    ps -p $pid -o %cpu,%mem,rss | tail -1 | awk '{printf "   CPU: %.1f%%  Memory: %.1f%% (%.0f MB)\n", $1, $2, $3/1024}'
else
    echo "   ✗ NOT RUNNING"
fi
echo

# Check disk space
echo "💾 Disk Space:"
df -h . | tail -1 | awk '{printf "   Used: %s / %s (%s)\n   Free: %s\n", $3, $2, $5, $4}'
echo

# Check recordings size
echo "📼 Recordings Storage:"
if [ -d "./recordings" ]; then
    du -sh recordings 2>/dev/null | awk '{print "   Total size: " $1}'
else
    echo "   Directory not found"
fi
echo

# Check recent errors (last 5 non-ONVIF errors)
echo "⚠️  Recent Errors (last 20 log lines):"
if [ -f "nvr.log" ]; then
    error_count=$(tail -100 nvr.log | grep -E "ERROR|CRITICAL" | grep -v "devicemgmt.wsdl" | wc -l | tr -d ' ')
    if [ "$error_count" -gt 0 ]; then
        echo "   Found $error_count error(s):"
        tail -100 nvr.log | grep -E "ERROR|CRITICAL" | grep -v "devicemgmt.wsdl" | tail -5 | sed 's/^/   → /'
    else
        echo "   ✓ No critical errors"
    fi
else
    echo "   Log file not found"
fi
echo

# Check system resources
echo "🖥️  System Resources:"
top -l 1 | grep "CPU usage" | awk '{printf "   CPU: %s user, %s sys, %s idle\n", $3, $5, $7}'
top -l 1 | grep "PhysMem" | awk '{printf "   Memory: %s used, %s free\n", $2, $6}'
echo

# Check monitoring status
echo "👁️  Continuous Monitor:"
if pgrep -f "monitor_system.py" > /dev/null; then
    echo "   ✓ Running"
    if [ -f "system_monitor.log" ]; then
        echo "   Last check: $(tail -1 system_monitor.log | cut -d']' -f1 | tr -d '[')"
    fi
else
    echo "   ✗ Not running (start with: python3 monitor_system.py &)"
fi
echo

echo "================================================================================"
echo "For continuous monitoring: tail -f system_monitor.log"
echo "To view monitoring dashboard: python3 monitor_system.py"
echo "================================================================================"
