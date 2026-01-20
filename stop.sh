#!/bin/bash

# SF-NVR Stop Script
# Gracefully stops the NVR server

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

PID_FILE="/tmp/nvr_server.pid"
PORT=8080

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}   SF-NVR - Shutdown${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${BLUE}⏸  Stopping NVR server (PID: $PID)...${NC}"
        kill "$PID" 2>/dev/null
        
        # Wait for graceful shutdown
        for i in {1..10}; do
            if ! ps -p "$PID" > /dev/null 2>&1; then
                echo -e "${GREEN}✓ Server stopped gracefully${NC}"
                rm -f "$PID_FILE"
                echo ""
                exit 0
            fi
            sleep 0.5
        done
        
        # Force kill if still running
        echo -e "${YELLOW}  Forcing shutdown...${NC}"
        kill -9 "$PID" 2>/dev/null || true
        rm -f "$PID_FILE"
        echo -e "${GREEN}✓ Server stopped (forced)${NC}"
    else
        echo -e "${YELLOW}⚠ Server not running (stale PID file)${NC}"
        rm -f "$PID_FILE"
    fi
else
    echo -e "${YELLOW}⚠ Server not running (no PID file)${NC}"
fi

# Clean up any processes on port 8080
if lsof -Pi :$PORT -sTCP:LISTEN -t > /dev/null 2>&1; then
    PORT_PID=$(lsof -ti:$PORT)
    echo -e "${YELLOW}  Cleaning up process on port $PORT (PID: $PORT_PID)...${NC}"
    kill -9 "$PORT_PID" 2>/dev/null || true
    echo -e "${GREEN}✓ Port $PORT freed${NC}"
fi

# Kill any remaining python3 NVR processes
pkill -9 -f "python3 main.py" 2>/dev/null && echo -e "${GREEN}✓ Cleaned up remaining processes${NC}" || true

# Clean up cached transcoded files to free disk space
if [ -d "recordings/.transcoded" ]; then
    FILE_COUNT=$(find recordings/.transcoded -name "*.mp4" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$FILE_COUNT" -gt 0 ]; then
        echo -e "${BLUE}  Cleaning up $FILE_COUNT cached transcoded files...${NC}"
        rm -rf recordings/.transcoded
        echo -e "${GREEN}✓ Freed disk space${NC}"
    fi
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Server stopped successfully${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
