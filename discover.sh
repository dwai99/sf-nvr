#!/bin/bash

# SF-NVR Discovery and Testing Script
# Runs comprehensive tests to validate NVR functionality

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

LOG_FILE="/tmp/nvr_server.log"
PORT=8080

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}   SF-NVR - Test Suite${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

TESTS_PASSED=0
TESTS_FAILED=0

# Test function
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -ne "${BLUE}→${NC} Testing: $test_name... "
    
    if eval "$test_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Test 1: Server Running
echo -e "${YELLOW}Server Health Checks:${NC}"
run_test "Server process running" "ps aux | grep -q 'python3 main.py' && ! grep -q '<defunct>'"
run_test "Port 8080 listening" "lsof -Pi :$PORT -sTCP:LISTEN -t > /dev/null"
run_test "Server responds to HTTP" "curl -s -m 3 http://localhost:$PORT/ > /dev/null"
echo ""

# Test 2: API Endpoints
echo -e "${YELLOW}API Endpoint Tests:${NC}"
run_test "GET /api/cameras" "curl -s -m 3 http://localhost:$PORT/api/cameras | python3 -c 'import sys,json; json.load(sys.stdin)'"
run_test "GET / (main page)" "curl -s -m 3 http://localhost:$PORT/ | grep -q 'SF-NVR'"
run_test "GET /api/status" "curl -s -m 3 http://localhost:$PORT/api/status > /dev/null"
echo ""

# Test 3: Camera Status
echo -e "${YELLOW}Camera Tests:${NC}"
CAMERA_COUNT=$(curl -s -m 3 http://localhost:$PORT/api/cameras 2>/dev/null | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null || echo "0")
RECORDING_COUNT=$(grep -c "Stream opened" "$LOG_FILE" 2>/dev/null || echo "0")

if [ "$CAMERA_COUNT" -gt 0 ]; then
    echo -e "${BLUE}→${NC} Cameras discovered: ${GREEN}$CAMERA_COUNT${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${BLUE}→${NC} Cameras discovered: ${RED}$CAMERA_COUNT${NC}"
    ((TESTS_FAILED++))
fi

if [ "$RECORDING_COUNT" -gt 0 ]; then
    echo -e "${BLUE}→${NC} Cameras streaming: ${GREEN}$RECORDING_COUNT${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${BLUE}→${NC} Cameras streaming: ${RED}$RECORDING_COUNT${NC}"
    ((TESTS_FAILED++))
fi

# Test a live stream endpoint if cameras exist
if [ "$CAMERA_COUNT" -gt 0 ]; then
    FIRST_CAMERA=$(curl -s -m 3 http://localhost:$PORT/api/cameras 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["name"])' 2>/dev/null)
    if [ -n "$FIRST_CAMERA" ]; then
        # Use Test camera which we know exists
        run_test "Live stream endpoint" "curl -s -m 2 'http://localhost:$PORT/api/cameras/Test/live?raw=true' | head -c 100 | od -c | grep -q '\\-'"
    fi
fi
echo ""

# Test 4: Logging & Error Checks
echo -e "${YELLOW}Error Checks:${NC}"
ERROR_COUNT=$(tail -100 "$LOG_FILE" 2>/dev/null | grep -c "ERROR" || echo "0")
CRITICAL_ERRORS=$(tail -100 "$LOG_FILE" 2>/dev/null | grep -E "(Traceback|Exception|CRITICAL)" | wc -l || echo "0")

if [ "$ERROR_COUNT" -lt 10 ]; then
    echo -e "${BLUE}→${NC} Recent errors: ${GREEN}$ERROR_COUNT${NC} (acceptable)"
    ((TESTS_PASSED++))
else
    echo -e "${BLUE}→${NC} Recent errors: ${YELLOW}$ERROR_COUNT${NC} (high)"
    ((TESTS_FAILED++))
fi

if [ "$CRITICAL_ERRORS" -eq 0 ]; then
    echo -e "${BLUE}→${NC} Critical errors: ${GREEN}0${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${BLUE}→${NC} Critical errors: ${RED}$CRITICAL_ERRORS${NC}"
    ((TESTS_FAILED++))
    echo -e "${YELLOW}Last critical error:${NC}"
    tail -100 "$LOG_FILE" | grep -E "(Traceback|Exception|CRITICAL)" | tail -3
fi
echo ""

# Test 5: Performance Metrics
echo -e "${YELLOW}Performance Metrics:${NC}"
RECORDINGS_DIR="recordings"
if [ -d "$RECORDINGS_DIR" ]; then
    RECORDING_SIZE=$(du -sh "$RECORDINGS_DIR" 2>/dev/null | awk '{print $1}')
    VIDEO_COUNT=$(find "$RECORDINGS_DIR" -name "*.mp4" 2>/dev/null | wc -l)
    echo -e "${BLUE}→${NC} Storage used: ${GREEN}$RECORDING_SIZE${NC}"
    echo -e "${BLUE}→${NC} Video segments: ${GREEN}$VIDEO_COUNT${NC}"
fi
echo ""

# Summary
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Test Summary${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}✓ Passed: $TESTS_PASSED${NC}"
echo -e "  ${RED}✗ Failed: $TESTS_FAILED${NC}"

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
if [ "$TOTAL_TESTS" -gt 0 ]; then
    SUCCESS_RATE=$(( (TESTS_PASSED * 100) / TOTAL_TESTS ))
    echo -e "  ${BLUE}→${NC} Success rate: ${SUCCESS_RATE}%"
fi
echo ""

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ Some tests failed${NC}"
    exit 1
fi
