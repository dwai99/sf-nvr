"""Configuration management for NVR"""

import os
import yaml
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Manages NVR configuration from YAML and environment variables"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            self._config = yaml.safe_load(f)

        # Ensure config is always a dictionary (yaml returns None for empty files)
        if self._config is None:
            self._config = {}

        # Ensure all cameras have unique IDs
        self._ensure_camera_ids()

    def save(self) -> None:
        """Save current configuration to YAML file"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Saving config to {self.config_path}")
        # Log camera names being saved
        cameras = self._config.get('cameras', [])
        camera_names = [c.get('name', 'unknown') for c in cameras]
        logger.info(f"Camera names being saved: {camera_names}")
        with open(self.config_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False)
        logger.info("Config saved successfully")

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-notation key (e.g., 'recording.storage_path')"""
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

        return value if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """Set config value by dot-notation key"""
        keys = key.split('.')
        config = self._config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    @property
    def storage_path(self) -> Path:
        """Get recordings storage path"""
        path = Path(self.get('recording.storage_path', './recordings'))
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cameras(self) -> List[Dict[str, Any]]:
        """Get list of configured cameras"""
        return self.get('cameras', [])

    @property
    def database_url(self) -> str:
        """Get database URL from environment or default"""
        return os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./nvr.db')

    @property
    def default_camera_username(self) -> str:
        """Get default camera username for ONVIF discovery"""
        return os.getenv('DEFAULT_CAMERA_USERNAME', 'admin')

    @property
    def default_camera_password(self) -> str:
        """Get default camera password for ONVIF discovery"""
        return os.getenv('DEFAULT_CAMERA_PASSWORD', 'admin')

    def add_camera(self, camera: Dict[str, Any]) -> None:
        """Add a new camera to configuration"""
        cameras = self.cameras
        cameras.append(camera)
        self.set('cameras', cameras)
        self.save()

    def remove_camera(self, name: str) -> bool:
        """Remove a camera by name"""
        cameras = self.cameras
        initial_len = len(cameras)
        cameras = [c for c in cameras if c.get('name') != name]

        if len(cameras) < initial_len:
            self.set('cameras', cameras)
            self.save()
            return True
        return False

    def _ensure_camera_ids(self) -> None:
        """Ensure all cameras have unique IDs, generate if missing or invalid"""
        cameras = self.cameras
        needs_save = False

        for camera in cameras:
            current_id = camera.get('id', '')
            # Regenerate if missing, empty, looks like a camera name, or uses IP-based ID
            # Valid IDs: cam_<serial>, cam_<mac>, cam_<hwid>, cam_<uuid>
            # Invalid IDs: camera names, cam_ip_* (IP-based)
            if not current_id or not current_id.startswith('cam_') or current_id.startswith('cam_ip_'):
                camera['id'] = self._generate_camera_id(camera)
                needs_save = True

        if needs_save:
            self.set('cameras', cameras)
            self.save()

    def _generate_camera_id(self, camera: Dict[str, Any]) -> str:
        """
        Generate a stable camera ID from physical identifiers

        Priority order:
        1. Serial number (best - physically tied to camera, survives DHCP changes)
        2. MAC address (excellent - hardware identifier, never changes)
        3. Hardware ID (if available from ONVIF)
        4. UUID as last resort (stable once generated)
        """
        device_info = camera.get('device_info', {})

        # Try serial number first (best option - physically tied to camera)
        serial = device_info.get('serial') or device_info.get('SerialNumber')
        if serial and serial not in ('Unknown', '', None):
            # Sanitize serial number for filesystem safety
            safe_serial = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in serial)
            return f"cam_{safe_serial}"

        # Try MAC address (permanent hardware identifier)
        mac = device_info.get('mac_address') or device_info.get('MACAddress')
        if mac and mac not in ('Unknown', '', None):
            # Convert MAC to safe format (aa:bb:cc:dd:ee:ff -> aabbccddeeff)
            safe_mac = mac.replace(':', '').replace('-', '').lower()
            return f"cam_{safe_mac}"

        # Try hardware ID
        hw_id = device_info.get('hardware_id') or device_info.get('HardwareId')
        if hw_id and hw_id not in ('Unknown', '', None):
            safe_hw = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in hw_id)
            return f"cam_{safe_hw}"

        # Last resort: generate UUID-based ID (stable once generated)
        return f"cam_{uuid.uuid4().hex[:12]}"

    def get_camera_by_id(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get camera configuration by ID"""
        for camera in self.cameras:
            if camera.get('id') == camera_id:
                return camera
        return None

    def get_camera_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get camera configuration by name"""
        for camera in self.cameras:
            if camera.get('name') == name:
                return camera
        return None

    def update_camera_name(self, camera_id: str, new_name: str) -> bool:
        """Update camera name while preserving ID"""
        cameras = self.cameras
        for camera in cameras:
            if camera.get('id') == camera_id:
                camera['name'] = new_name
                self.set('cameras', cameras)
                self.save()
                return True
        return False


# Global config instance
config = Config()