#!/bin/bash
# Live monitoring display - shows real-time status updates

echo "Starting live monitoring display... (Press Ctrl+C to stop)"
echo "Monitoring logs: system_monitor.log and system_alerts.log"
echo ""

# Show initial status
./check_status.sh
echo ""
echo "--- Live Updates (every 30 seconds) ---"
echo ""

# Follow both logs
tail -f system_monitor.log system_alerts.log 2>/dev/null
