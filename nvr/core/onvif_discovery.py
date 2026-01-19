"""ONVIF camera discovery and management"""

# Fix datetime.UTC for Python 3.9
from nvr.core import compat  # noqa

import asyncio
import logging
from typing import List, Dict, Optional, Any
from onvif import ONVIFCamera
from zeep.exceptions import Fault
import socket
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def get_wsdl_dir() -> str:
    """Find the WSDL directory for onvif-zeep"""
    try:
        import onvif
        onvif_path = Path(onvif.__file__).parent
        wsdl_path = onvif_path / 'wsdl'
        if wsdl_path.exists():
            return str(wsdl_path)
    except Exception:
        pass

    # Fallback to common locations
    possible_paths = [
        '/usr/local/lib/python3.11/site-packages/wsdl',
        '/usr/lib/python3/dist-packages/wsdl',
        str(Path.home() / '.local/lib/python3.11/site-packages/wsdl'),
    ]

    for path in possible_paths:
        if Path(path).exists():
            return path

    # Last resort - let onvif-zeep use its default
    return None


class ONVIFDevice:
    """Represents a discovered ONVIF camera"""

    def __init__(
        self,
        host: str,
        port: int = 80,
        username: str = 'admin',
        password: str = 'admin'
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.camera: Optional[ONVIFCamera] = None
        self.device_info: Dict[str, Any] = {}
        self.rtsp_urls: List[str] = []

    async def connect(self) -> bool:
        """Connect to ONVIF camera and retrieve information"""
        try:
            # Create ONVIF camera instance
            wsdl_dir = get_wsdl_dir()
            if wsdl_dir:
                self.camera = ONVIFCamera(
                    self.host,
                    self.port,
                    self.username,
                    self.password,
                    wsdl_dir=wsdl_dir
                )
            else:
                # Let library find WSDL automatically
                self.camera = ONVIFCamera(
                    self.host,
                    self.port,
                    self.username,
                    self.password
                )

            # Get device information
            device_mgmt = await asyncio.to_thread(self.camera.create_devicemgmt_service)
            device_info_obj = await asyncio.to_thread(device_mgmt.GetDeviceInformation)

            # Convert to dict
            self.device_info = {
                'Manufacturer': getattr(device_info_obj, 'Manufacturer', 'Unknown'),
                'Model': getattr(device_info_obj, 'Model', 'Unknown'),
                'FirmwareVersion': getattr(device_info_obj, 'FirmwareVersion', 'Unknown'),
                'SerialNumber': getattr(device_info_obj, 'SerialNumber', 'Unknown'),
                'HardwareId': getattr(device_info_obj, 'HardwareId', 'Unknown')
            }

            # Get RTSP URLs
            await self._get_rtsp_urls()

            logger.info(f"Connected to ONVIF camera at {self.host}:{self.port}")
            logger.info(f"Device: {self.device_info.get('Manufacturer', 'Unknown')} "
                       f"{self.device_info.get('Model', 'Unknown')}")

            return True

        except Fault as e:
            logger.error(f"ONVIF fault connecting to {self.host}:{self.port}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error connecting to {self.host}:{self.port}: {e}")
            return False

    async def _get_rtsp_urls(self) -> None:
        """Retrieve RTSP stream URLs from camera"""
        try:
            media_service = await asyncio.to_thread(self.camera.create_media_service)
            profiles = await asyncio.to_thread(media_service.GetProfiles)

            self.rtsp_urls = []
            for profile in profiles:
                try:
                    stream_uri = await asyncio.to_thread(
                        media_service.GetStreamUri,
                        {'StreamSetup': {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}},
                         'ProfileToken': profile.token}
                    )
                    self.rtsp_urls.append(stream_uri.Uri)
                except Exception as e:
                    logger.warning(f"Could not get stream URI for profile {profile.token}: {e}")

            logger.info(f"Found {len(self.rtsp_urls)} RTSP streams on {self.host}")

        except Exception as e:
            logger.error(f"Error getting RTSP URLs from {self.host}: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert device to dictionary for configuration"""
        manufacturer = self.device_info.get('Manufacturer', 'Unknown')
        model = self.device_info.get('Model', 'Unknown')
        serial = self.device_info.get('SerialNumber', 'Unknown')

        # Use serial number for camera name (permanent ID that survives DHCP changes)
        # Fallback to IP if serial not available
        if serial and serial != 'Unknown':
            camera_name = f"{manufacturer} {model} [{serial[-8:]}]"  # Last 8 chars of serial
        else:
            camera_name = f"{manufacturer} {model} ({self.host})"

        return {
            'name': camera_name,
            'rtsp_url': self.rtsp_urls[0] if self.rtsp_urls else f"rtsp://{self.host}:554/stream1",
            'onvif_host': self.host,
            'onvif_port': self.port,
            'username': self.username,
            'password': self.password,
            'enabled': True,
            'device_info': {
                'manufacturer': manufacturer,
                'model': model,
                'firmware': self.device_info.get('FirmwareVersion', 'Unknown'),
                'serial': serial
            }
        }


class ONVIFDiscovery:
    """Discovers ONVIF cameras on the local network"""

    def __init__(self, username: str = 'admin', password: str = 'admin'):
        self.username = username
        self.password = password

    async def discover_cameras(
        self,
        timeout: int = 5,
        scan_range: Optional[str] = None
    ) -> List[ONVIFDevice]:
        """
        Discover ONVIF cameras on network

        Args:
            timeout: Discovery timeout in seconds
            scan_range: IP range to scan (e.g., "192.168.1.0/24"), None for WS-Discovery

        Returns:
            List of discovered ONVIF devices
        """
        if scan_range:
            return await self._scan_ip_range(scan_range, timeout)
        else:
            return await self._ws_discovery(timeout)

    async def _ws_discovery(self, timeout: int) -> List[ONVIFDevice]:
        """
        Use WS-Discovery to find ONVIF cameras
        Note: This is a simplified version. Full implementation would use WSDiscovery protocol
        """
        logger.info("WS-Discovery not yet implemented, using IP scan fallback")
        # For now, fall back to scanning common subnet
        local_ip = self._get_local_ip()
        if local_ip:
            subnet = '.'.join(local_ip.split('.')[:-1]) + '.0/24'
            return await self._scan_ip_range(subnet, timeout)
        return []

    async def _scan_ip_range(self, ip_range: str, timeout: int) -> List[ONVIFDevice]:
        """Scan IP range for ONVIF cameras"""
        logger.info(f"Scanning {ip_range} for ONVIF cameras...")

        # Parse CIDR notation
        base_ip, prefix = ip_range.split('/')
        prefix = int(prefix)

        if prefix != 24:
            logger.warning("Only /24 subnets currently supported")
            return []

        base = '.'.join(base_ip.split('.')[:-1])

        # Try common ONVIF ports
        devices = []

        # Phase 1: Quick scan on common ONVIF ports
        # Port 80 (standard), 8089 (Night Owl), 8080, 8000 (alternatives)
        logger.info("Phase 1: Scanning common ONVIF ports (80, 8089, 8080, 8000)...")
        responsive_targets = await self._quick_port_scan(base, [80, 8089, 8080, 8000])
        logger.info(f"Found {len(responsive_targets)} responsive device(s)")

        if not responsive_targets:
            logger.info("No responsive hosts found")
            return []

        # Then try ONVIF connection on responsive hosts
        logger.info("Phase 2: Testing ONVIF connections...")

        # Use shorter timeout for local network (2s is plenty)
        onvif_timeout = min(timeout, 2)

        for idx, (ip, port) in enumerate(responsive_targets, 1):
            logger.info(f"Testing {ip}:{port} ({idx}/{len(responsive_targets)})...")
            try:
                device = ONVIFDevice(ip, port, self.username, self.password)
                connected = await asyncio.wait_for(
                    device.connect(),
                    timeout=onvif_timeout
                )
                if connected:
                    devices.append(device)
                    logger.info(f"✓ Found ONVIF camera at {ip}:{port}")
            except asyncio.TimeoutError:
                logger.debug(f"Timeout connecting to {ip}:{port}")
            except Exception as e:
                logger.debug(f"Error connecting to {ip}:{port}: {e}")

        logger.info(f"Discovery complete: found {len(devices)} ONVIF camera(s)")
        return devices

    async def _quick_port_scan(self, base: str, ports: List[int]) -> List[tuple]:
        """Quick TCP port scan to find responsive hosts using asyncio"""
        responsive = []

        # Create all scanning tasks - run them ALL in parallel
        tasks = []
        for i in range(1, 255):
            ip = f"{base}.{i}"
            for port in ports:
                tasks.append(self._check_port_async(ip, port))

        logger.info(f"Scanning {len(tasks)} IP/port combinations in parallel...")

        # Run all tasks concurrently with a short timeout
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful connections
        for result in results:
            if result and isinstance(result, tuple):
                responsive.append(result)

        return responsive

    async def _check_port_async(self, ip: str, port: int) -> Optional[tuple]:
        """Async check if port is open using asyncio streams"""
        try:
            # Use asyncio.open_connection with very short timeout
            conn = asyncio.open_connection(ip, port)
            reader, writer = await asyncio.wait_for(conn, timeout=0.2)

            # Port is open, close connection immediately
            writer.close()
            await writer.wait_closed()

            return (ip, port)

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            # Port closed or timeout - this is expected for most IPs
            pass
        except Exception:
            # Any other error, skip this host
            pass

        return None


    def _get_local_ip(self) -> Optional[str]:
        """Get local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None