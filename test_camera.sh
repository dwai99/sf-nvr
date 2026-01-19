#!/bin/bash
# Quick camera connectivity test

echo "======================================"
echo "  Camera Connectivity Test"
echo "======================================"
echo ""

CAMERA_IP="192.168.0.76"

echo "Testing camera: $CAMERA_IP"
echo ""

# Test ping
echo "1. Testing ping..."
if ping -c 3 $CAMERA_IP > /dev/null 2>&1; then
    echo "   ✓ Camera is reachable"
else
    echo "   ✗ Camera is NOT reachable (check IP/network)"
    exit 1
fi
echo ""

# Test common ports
echo "2. Testing ports..."
for port in 80 554 8080 8000 8089; do
    if nc -z -w 2 $CAMERA_IP $port 2>/dev/null; then
        echo "   ✓ Port $port is OPEN"
    else
        echo "   - Port $port is closed"
    fi
done
echo ""

# Test ONVIF endpoint
echo "3. Testing ONVIF endpoint on port 8089..."
response=$(curl -s -m 2 "http://$CAMERA_IP:8089/onvif/device_service" 2>/dev/null || echo "failed")
if [ "$response" != "failed" ]; then
    echo "   ✓ ONVIF endpoint responds"
else
    echo "   ✗ ONVIF endpoint did not respond"
fi
echo ""

# Test RTSP
echo "4. Testing RTSP stream..."
echo "   Attempting to connect to rtsp://$CAMERA_IP:554/ch0_1.264"
echo "   (This will take a few seconds...)"
timeout 5 ffplay -rtsp_transport tcp -i "rtsp://$CAMERA_IP:554/ch0_1.264" -nodisp -autoexit 2>&1 | head -n 5
if [ $? -eq 0 ] || [ $? -eq 124 ]; then
    echo "   ✓ RTSP stream is accessible"
else
    echo "   ✗ RTSP stream failed (check credentials in stream URL)"
fi
echo ""

echo "======================================"
echo "Test complete!"
echo "======================================"
