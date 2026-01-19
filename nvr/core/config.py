"""Configuration management for NVR"""

import os
import yaml
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

    def save(self) -> None:
        """Save current configuration to YAML file"""
        with open(self.config_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False)

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


# Global config instance
config = Config()