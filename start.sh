#!/bin/bash

# SF-NVR Start Script
# Starts the NVR server with detailed status information

set -e

# Colors for pretty output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

LOG_FILE="/tmp/nvr_server.log"
PID_FILE="/tmp/nvr_server.pid"
PORT=8080

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}   SF-NVR - Network Video Recorder${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if server is already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠ Server is already running (PID: $PID)${NC}"
        echo -e "  ${BLUE}→${NC} http://localhost:$PORT"
        echo ""
        exit 1
    else
        echo -e "${YELLOW}⚠ Cleaning up stale PID file${NC}"
        rm -f "$PID_FILE"
    fi
fi

# Check if port is in use
if lsof -Pi :$PORT -sTCP:LISTEN -t > /dev/null 2>&1; then
    PORT_PID=$(lsof -ti:$PORT)
    echo -e "${YELLOW}⚠ Port $PORT is already in use by PID $PORT_PID${NC}"
    echo -e "${YELLOW}  Killing process...${NC}"
    kill -9 "$PORT_PID" 2>/dev/null || true
    sleep 1
    echo -e "${GREEN}✓ Port $PORT freed${NC}"
    echo ""
fi

# Start the server
echo -e "${BLUE}▶ Starting NVR server...${NC}"
echo -e "  ${BLUE}→${NC} Log file: $LOG_FILE"
echo ""

# Set OpenCV environment variable for TCP RTSP transport with latency tolerance
# timeout: 60 seconds for initial connection (handles high latency networks)
# stimeout: 10 seconds per packet (handles intermittent delays)
# max_delay: 10 seconds buffer for network jitter
export OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp|timeout;60000000|stimeout;10000000|max_delay;10000000"

python3 main.py > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

echo -e "${GREEN}✓ Server started (PID: $SERVER_PID)${NC}"
echo ""

# Wait for server to initialize
echo -e "${BLUE}⏳ Waiting for server initialization...${NC}"
sleep 3

# Check if process is still running
if ! ps -p "$SERVER_PID" > /dev/null 2>&1; then
    echo -e "${RED}✗ Server failed to start!${NC}"
    echo -e "${YELLOW}Last 20 log lines:${NC}"
    tail -20 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi

# Monitor startup for server ready
echo -n "Waiting for server"
for i in {1..15}; do
    if grep -q "Uvicorn running" "$LOG_FILE" 2>/dev/null; then
        echo ""
        echo -e "${GREEN}✓ Server is ready!${NC}"
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

# Wait and monitor camera connections
echo -e "${BLUE}⏳ Monitoring camera connections (up to 15s)...${NC}"
echo ""

MONITOR_START=$(date +%s)
MONITOR_DURATION=15
LAST_COUNT=0
SHOWN_CAMERAS=""

while true; do
    CURRENT_COUNT=$(grep -c "Stream opened" "$LOG_FILE" 2>/dev/null | tr -d ' \n' || echo "0")
    ELAPSED=$(($(date +%s) - MONITOR_START))

    # Show progress if new cameras connected
    if [ "$CURRENT_COUNT" -gt "$LAST_COUNT" ] 2>/dev/null; then
        # Get newly connected cameras (not already shown)
        CONNECTED_NOW=$(grep -B1 "Stream opened" "$LOG_FILE" | grep "Connecting to" | sed -n 's/.*Connecting to \(.*\)\.\.\./\1/p' | sort -u)

        echo "$CONNECTED_NOW" | while read camera; do
            # Only show if we haven't shown this camera yet
            if [ ! -z "$camera" ] && ! echo "$SHOWN_CAMERAS" | grep -q "^$camera$"; then
                echo -e "  ${GREEN}✓${NC} $camera"
                SHOWN_CAMERAS="$SHOWN_CAMERAS"$'\n'"$camera"
            fi
        done

        LAST_COUNT=$CURRENT_COUNT
    fi

    # Check if we've waited long enough
    if [ "$ELAPSED" -ge "$MONITOR_DURATION" ]; then
        break
    fi

    sleep 1
done

echo ""

# Count total cameras and connected cameras
CAMERA_COUNT=$(grep -c "Stream opened" "$LOG_FILE" 2>/dev/null | tr -d ' \n' || echo "0")
TOTAL_CAMERAS=$(grep "Started recording on" "$LOG_FILE" 2>/dev/null | grep -o '[0-9]\+' | head -1 | tr -d ' \n' || echo "0")

# Display startup summary
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Server Status${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

echo -e "  ${BLUE}→${NC} PID: ${GREEN}$SERVER_PID${NC}"
echo -e "  ${BLUE}→${NC} URL: ${GREEN}http://localhost:$PORT${NC}"
echo -e "  ${BLUE}→${NC} Cameras: ${GREEN}$CAMERA_COUNT${NC}/${TOTAL_CAMERAS} connected"
echo -e "  ${BLUE}→${NC} Mode: ${GREEN}TCP transport (reliable)${NC}"
echo -e "  ${BLUE}→${NC} Streaming: ${GREEN}Direct RTSP proxy (ultra-fast)${NC}"
echo ""

# Show which cameras are connected
if [ "$CAMERA_COUNT" -gt 0 ]; then
    echo -e "${GREEN}Connected cameras:${NC}"
    # Match "Stream opened" lines with their preceding "Connecting to" lines
    grep -B1 "Stream opened" "$LOG_FILE" | grep "Connecting to" | sed -n 's/.*Connecting to \(.*\)\.\.\./\1/p' | sort -u | while read camera; do
        if [ ! -z "$camera" ]; then
            echo -e "  ${GREEN}✓${NC} $camera"
        fi
    done
    echo ""
fi

# Show cameras that failed to connect
FAILED_COUNT=$((TOTAL_CAMERAS - CAMERA_COUNT))
if [ "$FAILED_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}Cameras still connecting or failed (will retry):${NC}"
    # Find cameras that are "Connecting" but don't have "Stream opened" yet
    ALL_CAMERAS=$(grep "Connecting to" "$LOG_FILE" | sed -n 's/.*Connecting to \(.*\)\.\.\./\1/p' | sort -u)
    CONNECTED_CAMERAS=$(grep -B1 "Stream opened" "$LOG_FILE" | grep "Connecting to" | sed -n 's/.*Connecting to \(.*\)\.\.\./\1/p' | sort -u)

    # Show cameras that haven't connected yet
    echo "$ALL_CAMERAS" | while read camera; do
        if ! echo "$CONNECTED_CAMERAS" | grep -q "^$camera$"; then
            echo -e "  ${YELLOW}⏳${NC} $camera"
        fi
    done
    echo ""
fi

# Show initialization details
if grep -q "RTSP Direct Proxy initialized" "$LOG_FILE" 2>/dev/null; then
    echo -e "${GREEN}✓ RTSP Direct Proxy initialized${NC}"
fi
if grep -q "WebRTC.*passthrough" "$LOG_FILE" 2>/dev/null; then
    echo -e "${GREEN}✓ WebRTC H.264 passthrough ready${NC}"
fi
echo ""

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Commands:${NC}"
echo -e "  ${BLUE}→${NC} Stop server:    ./stop.sh"
echo -e "  ${BLUE}→${NC} Restart server: ./restart.sh"
echo -e "  ${BLUE}→${NC} View logs:      tail -f $LOG_FILE"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
