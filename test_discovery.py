#!/usr/bin/env python3
"""
Quick test script to debug discovery issues
"""

import asyncio
import logging
import sys

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,  # DEBUG to see everything
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

from nvr.core.config import config
from nvr.core.onvif_discovery import ONVIFDiscovery


async def test_port_scan():
    """Test just the port scanning part"""
    print("=" * 60)
    print("  Testing Port Scan")
    print("=" * 60)
    print()

    discovery = ONVIFDiscovery(
        username=config.default_camera_username,
        password=config.default_camera_password
    )

    # Get local IP
    local_ip = discovery._get_local_ip()
    print(f"Local IP: {local_ip}")

    if not local_ip:
        print("ERROR: Could not detect local IP")
        return

    base = '.'.join(local_ip.split('.')[:-1])
    print(f"Scanning base: {base}.X")
    print()

    # Test specific IP first (your camera)
    print("Testing your known camera IP 192.168.0.76...")
    result = await discovery._check_port_async('192.168.0.76', 8089)
    print(f"Result for 192.168.0.76:8089: {result}")
    print()

    # Quick scan
    print("Running quick port scan...")
    responsive = await discovery._quick_port_scan(base, [80, 8089, 8080, 8000])
    print(f"\nFound {len(responsive)} responsive device(s):")
    for ip, port in responsive:
        print(f"  - {ip}:{port}")


async def test_onvif_connect():
    """Test ONVIF connection to known camera"""
    print()
    print("=" * 60)
    print("  Testing ONVIF Connection")
    print("=" * 60)
    print()

    from nvr.core.onvif_discovery import ONVIFDevice

    print("Attempting to connect to 192.168.0.76:8089...")

    device = ONVIFDevice(
        host='192.168.0.76',
        port=8089,
        username=config.default_camera_username,
        password=config.default_camera_password
    )

    try:
        connected = await asyncio.wait_for(device.connect(), timeout=5)
        if connected:
            print("✓ Successfully connected!")
            print(f"Device Info: {device.device_info}")
            print(f"RTSP URLs: {device.rtsp_urls}")
        else:
            print("✗ Connection failed")
    except asyncio.TimeoutError:
        print("✗ Connection timeout")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Run all tests"""
    try:
        await test_port_scan()
        await test_onvif_connect()
    except KeyboardInterrupt:
        print("\n\nTest cancelled")
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
