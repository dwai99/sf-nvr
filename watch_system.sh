#!/bin/bash
# Continuous system monitoring with alerts
# Run with: ./watch_system.sh &

LOG_FILE="system_monitor.log"
CHECK_INTERVAL=30
ALERT_LOG="system_alerts.log"

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_alert() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ALERT: $1" | tee -a "$ALERT_LOG" >> "$LOG_FILE"
}

log_message "=== System monitoring started ==="

while true; do
    # Check NVR process
    if ! pgrep -f "main.py" > /dev/null; then
        log_alert "NVR process is NOT running!"
    fi

    # Check disk space
    disk_usage=$(df . | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$disk_usage" -ge 95 ]; then
        log_alert "Disk space CRITICAL: ${disk_usage}% used"
    elif [ "$disk_usage" -ge 85 ]; then
        log_alert "Disk space WARNING: ${disk_usage}% used"
    fi

    # Check for errors in NVR log
    if [ -f "nvr.log" ]; then
        error_count=$(tail -50 nvr.log | grep -E "ERROR|CRITICAL" | grep -v "devicemgmt.wsdl" | wc -l | tr -d ' ')
        if [ "$error_count" -gt 0 ]; then
            log_message "Found $error_count error(s) in last 50 log lines"
            tail -50 nvr.log | grep -E "ERROR|CRITICAL" | grep -v "devicemgmt.wsdl" | tail -3 | while read line; do
                log_message "  ERROR: $line"
            done
        fi
    fi

    # Check memory usage
    mem_usage=$(top -l 1 | grep PhysMem | awk '{print $2}' | sed 's/G//')
    log_message "Status: NVR running, Disk ${disk_usage}%, Memory ${mem_usage}G used"

    sleep "$CHECK_INTERVAL"
done
