#!/bin/bash

# SF-NVR Status Script
# Check if the NVR server is running

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

PID_FILE="/tmp/nvr_server.pid"
PORT=8080

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}   SF-NVR Server Status${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")

    # Check if process is running
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}● Server is RUNNING${NC}"
        echo ""
        echo -e "  ${BLUE}PID:${NC}  $PID"
        echo -e "  ${BLUE}URL:${NC}  http://localhost:$PORT"

        # Get process uptime
        if command -v ps &> /dev/null; then
            UPTIME=$(ps -o etime= -p "$PID" 2>/dev/null | tr -d ' ')
            if [ -n "$UPTIME" ]; then
                echo -e "  ${BLUE}Uptime:${NC} $UPTIME"
            fi
        fi

        # Check if port is actually listening
        if lsof -Pi :$PORT -sTCP:LISTEN -t > /dev/null 2>&1; then
            echo -e "  ${BLUE}Port:${NC}  $PORT ${GREEN}(listening)${NC}"
        else
            echo -e "  ${BLUE}Port:${NC}  $PORT ${YELLOW}(not listening yet)${NC}"
        fi

        # Try to get camera count from API
        if command -v curl &> /dev/null; then
            CAMERA_INFO=$(curl -s --connect-timeout 2 "http://localhost:$PORT/api/cameras" 2>/dev/null)
            if [ -n "$CAMERA_INFO" ]; then
                TOTAL=$(echo "$CAMERA_INFO" | grep -o '"name"' | wc -l | tr -d ' ')
                RECORDING=$(echo "$CAMERA_INFO" | grep -o '"recording": true' | wc -l | tr -d ' ')
                echo -e "  ${BLUE}Cameras:${NC} $RECORDING recording / $TOTAL total"
            fi
        fi

        # Show log file location
        CONFIG_FILE="config/config.yaml"
        if [ -f "$CONFIG_FILE" ]; then
            LOG_FILE=$(grep -A1 "^logging:" "$CONFIG_FILE" 2>/dev/null | grep "file:" | sed 's/.*file:\s*//' | tr -d ' "'"'" || echo "./logs/nvr.log")
            [ -z "$LOG_FILE" ] && LOG_FILE="./logs/nvr.log"
        else
            LOG_FILE="./logs/nvr.log"
        fi
        echo -e "  ${BLUE}Logs:${NC}  $LOG_FILE"

        echo ""
        exit 0
    else
        echo -e "${YELLOW}● Server is NOT RUNNING${NC} (stale PID file)"
        echo ""
        echo -e "  PID $PID is no longer running."
        echo -e "  Run ${GREEN}./start.sh${NC} to start the server."
        echo ""
        exit 1
    fi
else
    # No PID file - check if something is on the port anyway
    if lsof -Pi :$PORT -sTCP:LISTEN -t > /dev/null 2>&1; then
        PORT_PID=$(lsof -ti:$PORT 2>/dev/null)
        echo -e "${YELLOW}● Server may be running${NC} (no PID file)"
        echo ""
        echo -e "  Port $PORT is in use by PID: $PORT_PID"
        echo -e "  This might be the NVR server started manually."
        echo ""
        exit 0
    else
        echo -e "${RED}● Server is STOPPED${NC}"
        echo ""
        echo -e "  Run ${GREEN}./start.sh${NC} to start the server."
        echo ""
        exit 1
    fi
fi
