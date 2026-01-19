#!/usr/bin/env python3
"""
Quick ONVIF camera discovery tool
Use this to find cameras without starting the full NVR
"""

import asyncio
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

from nvr.core.config import config
from nvr.core.onvif_discovery import ONVIFDiscovery


async def main():
    """Discover cameras and display results"""
    print("=" * 60)
    print("  ONVIF Camera Discovery Tool")
    print("=" * 60)
    print()

    # Get credentials
    username = config.default_camera_username
    password = config.default_camera_password

    print(f"Using credentials: {username}:{('*' * len(password))}")
    print()

    # Auto-detect local subnet
    discovery = ONVIFDiscovery(username=username, password=password)
    local_ip = discovery._get_local_ip()

    if local_ip:
        subnet = '.'.join(local_ip.split('.')[:-1]) + '.0/24'
        print(f"Auto-detected subnet: {subnet}")
        print(f"Your IP: {local_ip}")
    else:
        subnet = None
        print("Could not auto-detect subnet")

    # Use detected subnet automatically
    ip_range = subnet
    print()
    if ip_range:
        print(f"Scanning {ip_range}...")
    else:
        print("Using WS-Discovery...")
    print()

    # Discover cameras
    try:
        timeout = config.get('onvif.discovery_timeout', 5)
        devices = await discovery.discover_cameras(timeout=timeout, scan_range=ip_range)

        print()
        print("=" * 60)
        print(f"  Discovery Complete - Found {len(devices)} camera(s)")
        print("=" * 60)
        print()

        if devices:
            for idx, device in enumerate(devices, 1):
                info = device.device_info
                print(f"Camera {idx}:")
                print(f"  IP Address: {device.host}:{device.port}")
                print(f"  Manufacturer: {info.get('Manufacturer', 'Unknown')}")
                print(f"  Model: {info.get('Model', 'Unknown')}")
                print(f"  Firmware: {info.get('FirmwareVersion', 'Unknown')}")
                print(f"  Serial: {info.get('SerialNumber', 'Unknown')}")
                print(f"  RTSP URLs:")
                for url in device.rtsp_urls:
                    print(f"    - {url}")
                print()

            # Auto-save cameras to config
            print()
            print("Saving cameras to config.yaml...")

            for device in devices:
                camera_dict = device.to_dict()
                config.add_camera(camera_dict)
                print(f"✓ Added {camera_dict['name']}")

            print()
            print(f"✓ {len(devices)} camera(s) saved to {config.config_path}")
            print()
            print("Start NVR with: ./start.sh")

        else:
            print("No cameras found.")
            print()
            print("Troubleshooting tips:")
            print("  1. Ensure cameras are powered on and connected to network")
            print("  2. Check that cameras are on the same subnet")
            print("  3. Verify ONVIF is enabled in camera settings")
            print("  4. Try different credentials in .env file")
            print("  5. Check firewall settings")

    except KeyboardInterrupt:
        print("\n\nDiscovery cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error during discovery: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
