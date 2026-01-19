#!/bin/bash

# Streaming Performance Test Suite
# Tests all streaming modes and identifies bottlenecks

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

BASE_URL="http://localhost:8080"
PASSED=0
FAILED=0
WARNINGS=0

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}   NVR Streaming Performance Test Suite${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${CYAN}━━━ 1. Get Available Cameras ━━━${NC}"
echo ""

CAMERAS=$(curl -s "$BASE_URL/api/cameras" | python3 -c "import sys, json; cameras = json.load(sys.stdin); print('\n'.join([c['name'] for c in cameras if c['recording']]))" 2>/dev/null)

if [ -z "$CAMERAS" ]; then
    echo -e "${RED}✗ No cameras available for testing${NC}"
    exit 1
fi

CAMERA_COUNT=$(echo "$CAMERAS" | wc -l | tr -d ' ')
echo -e "${GREEN}✓ Found $CAMERA_COUNT cameras recording${NC}"
echo "$CAMERAS" | while read cam; do
    echo "  • $cam"
done

# Pick first camera for detailed tests
TEST_CAMERA=$(echo "$CAMERAS" | head -1)
echo ""
echo -e "${YELLOW}Using camera: $TEST_CAMERA${NC}"

echo ""
echo -e "${CYAN}━━━ 2. MJPEG Streaming Tests ━━━${NC}"
echo ""

# Test low quality MJPEG (default for grid)
echo -e "${BLUE}Testing: MJPEG Low Quality (grid default)${NC}"
START=$(date +%s%N)
TTFB=$(curl -s -w "%{time_starttransfer}" -m 10 -o /dev/null "$BASE_URL/api/cameras/$TEST_CAMERA/live?quality=40&raw=true" 2>&1)
END=$(date +%s%N)
TTFB_MS=$(echo "scale=0; $TTFB * 1000 / 1" | bc)

echo -e "  ${GREEN}✓${NC} Time to first byte: ${TTFB_MS}ms"

if (( $(echo "$TTFB > 2.0" | bc -l) )); then
    echo -e "  ${RED}✗${NC} SLOW: >2s to first frame!"
    ((FAILED++))
elif (( $(echo "$TTFB > 1.0" | bc -l) )); then
    echo -e "  ${YELLOW}⚠${NC} Slow: >1s to first frame"
    ((WARNINGS++))
else
    echo -e "  ${GREEN}✓${NC} Good startup time"
    ((PASSED++))
fi

# Test sustained streaming
echo -e "  ${BLUE}→${NC} Testing sustained streaming (5s)..."
BYTES=$(timeout 5 curl -s "$BASE_URL/api/cameras/$TEST_CAMERA/live?quality=40&raw=true" 2>/dev/null | wc -c)
BYTES_PER_SEC=$((BYTES / 5))
KB_PER_SEC=$((BYTES_PER_SEC / 1024))

echo -e "  ${GREEN}✓${NC} Data rate: ${KB_PER_SEC} KB/s"

if [ "$KB_PER_SEC" -lt 10 ]; then
    echo -e "  ${RED}✗${NC} VERY LOW data rate (<10 KB/s)"
    ((FAILED++))
elif [ "$KB_PER_SEC" -lt 50 ]; then
    echo -e "  ${YELLOW}⚠${NC} Low data rate (<50 KB/s)"
    ((WARNINGS++))
else
    ((PASSED++))
fi

echo ""

# Test medium quality
echo -e "${BLUE}Testing: MJPEG Medium Quality${NC}"
START=$(date +%s%N)
TTFB=$(curl -s -w "%{time_starttransfer}" -m 10 -o /dev/null "$BASE_URL/api/cameras/$TEST_CAMERA/live?quality=65&raw=true" 2>&1)
TTFB_MS=$(echo "scale=0; $TTFB * 1000 / 1" | bc)

echo -e "  ${GREEN}✓${NC} Time to first byte: ${TTFB_MS}ms"

if (( $(echo "$TTFB > 2.0" | bc -l) )); then
    echo -e "  ${RED}✗${NC} SLOW: >2s to first frame!"
    ((FAILED++))
elif (( $(echo "$TTFB > 1.0" | bc -l) )); then
    echo -e "  ${YELLOW}⚠${NC} Slow: >1s to first frame"
    ((WARNINGS++))
else
    ((PASSED++))
fi

echo ""

# Test high quality (fullscreen)
echo -e "${BLUE}Testing: MJPEG High Quality (fullscreen default)${NC}"
START=$(date +%s%N)
TTFB=$(curl -s -w "%{time_starttransfer}" -m 10 -o /dev/null "$BASE_URL/api/cameras/$TEST_CAMERA/live?quality=90&raw=true" 2>&1)
TTFB_MS=$(echo "scale=0; $TTFB * 1000 / 1" | bc)

echo -e "  ${GREEN}✓${NC} Time to first byte: ${TTFB_MS}ms"

if (( $(echo "$TTFB > 2.0" | bc -l) )); then
    echo -e "  ${RED}✗${NC} SLOW: >2s to first frame!"
    ((FAILED++))
elif (( $(echo "$TTFB > 1.0" | bc -l) )); then
    echo -e "  ${YELLOW}⚠${NC} Slow: >1s to first frame"
    ((WARNINGS++))
else
    ((PASSED++))
fi

# Test sustained high quality
echo -e "  ${BLUE}→${NC} Testing sustained high quality (5s)..."
BYTES=$(timeout 5 curl -s "$BASE_URL/api/cameras/$TEST_CAMERA/live?quality=90&raw=true" 2>/dev/null | wc -c)
BYTES_PER_SEC=$((BYTES / 5))
KB_PER_SEC=$((BYTES_PER_SEC / 1024))

echo -e "  ${GREEN}✓${NC} Data rate: ${KB_PER_SEC} KB/s"

if [ "$KB_PER_SEC" -lt 20 ]; then
    echo -e "  ${RED}✗${NC} VERY LOW data rate for high quality"
    ((FAILED++))
elif [ "$KB_PER_SEC" -lt 100 ]; then
    echo -e "  ${YELLOW}⚠${NC} Low data rate for high quality"
    ((WARNINGS++))
else
    ((PASSED++))
fi

echo ""
echo -e "${CYAN}━━━ 3. Direct RTSP Proxy Test ━━━${NC}"
echo ""

echo -e "${BLUE}Testing: Direct RTSP proxy (ultra-low latency)${NC}"
TTFB=$(curl -s -w "%{time_starttransfer}" -m 10 -o /dev/null "$BASE_URL/api/cameras/$TEST_CAMERA/stream/direct" 2>&1)
TTFB_MS=$(echo "scale=0; $TTFB * 1000 / 1" | bc)

echo -e "  ${GREEN}✓${NC} Time to first byte: ${TTFB_MS}ms"

if (( $(echo "$TTFB > 0.5" | bc -l) )); then
    echo -e "  ${YELLOW}⚠${NC} Direct mode should be <500ms"
    ((WARNINGS++))
else
    echo -e "  ${GREEN}✓${NC} Excellent latency!"
    ((PASSED++))
fi

echo ""
echo -e "${CYAN}━━━ 4. Concurrent Streaming Test ━━━${NC}"
echo ""

echo -e "${BLUE}Testing: 5 concurrent low quality streams${NC}"
START=$(date +%s)
(
    for i in {1..5}; do
        timeout 3 curl -s "$BASE_URL/api/cameras/$TEST_CAMERA/live?quality=40&raw=true" > /dev/null &
    done
    wait
)
END=$(date +%s)
DURATION=$((END - START))

echo -e "  ${GREEN}✓${NC} Concurrent streams completed in ${DURATION}s"

if [ "$DURATION" -gt 5 ]; then
    echo -e "  ${RED}✗${NC} Too slow for concurrent streams"
    ((FAILED++))
elif [ "$DURATION" -gt 4 ]; then
    echo -e "  ${YELLOW}⚠${NC} Borderline performance"
    ((WARNINGS++))
else
    echo -e "  ${GREEN}✓${NC} Good concurrent performance"
    ((PASSED++))
fi

echo ""
echo -e "${CYAN}━━━ 5. Backend Performance Check ━━━${NC}"
echo ""

LOG_FILE="/tmp/nvr_server.log"
if [ -f "$LOG_FILE" ]; then
    # Count frame read failures
    RECENT_FAILURES=$(grep "Failed to read frame" "$LOG_FILE" | tail -100 | wc -l | tr -d ' ')

    if [ "$RECENT_FAILURES" -gt 20 ]; then
        echo -e "  ${RED}✗${NC} High frame failure rate: $RECENT_FAILURES recent failures"
        ((FAILED++))
    elif [ "$RECENT_FAILURES" -gt 5 ]; then
        echo -e "  ${YELLOW}⚠${NC} Some frame failures: $RECENT_FAILURES recent"
        ((WARNINGS++))
    else
        echo -e "  ${GREEN}✓${NC} Low frame failure rate: $RECENT_FAILURES recent"
        ((PASSED++))
    fi

    # Check for connection errors
    CONN_ERRORS=$(grep -c "Failed to open RTSP" "$LOG_FILE" 2>/dev/null || echo "0")
    echo -e "  ${BLUE}→${NC} RTSP connection failures: $CONN_ERRORS total"

    # Show recent errors
    RECENT_ERRORS=$(grep "ERROR" "$LOG_FILE" | tail -5)
    if [ ! -z "$RECENT_ERRORS" ]; then
        echo ""
        echo -e "${YELLOW}Recent errors (last 5):${NC}"
        echo "$RECENT_ERRORS" | while read line; do
            echo -e "  ${RED}→${NC} $(echo $line | cut -c 1-100)"
        done
    fi
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Performance Summary${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}✓${NC} Passed:   $PASSED"
echo -e "  ${RED}✗${NC} Failed:   $FAILED"
echo -e "  ${YELLOW}⚠${NC} Warnings: $WARNINGS"
echo ""

if [ "$FAILED" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed with excellent performance!${NC}"
    exit 0
elif [ "$FAILED" -eq 0 ]; then
    echo -e "${YELLOW}All tests passed but with $WARNINGS warnings${NC}"
    echo -e "Consider optimizing further for production use"
    exit 0
else
    echo -e "${RED}❌ Performance issues detected${NC}"
    echo -e "Review the test results above to identify bottlenecks"
    exit 1
fi
