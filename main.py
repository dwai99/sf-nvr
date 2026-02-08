#!/usr/bin/env python3
"""
SF-NVR - Network Video Recorder
Main entry point for the application
"""

# CRITICAL: Set OpenCV environment variables BEFORE any imports
# OpenCV reads these on first use, so they must be set at the very start
import os
os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|timeout;60000000|stimeout;10000000|max_delay;10000000'
# Suppress OpenCV FFmpeg warnings
os.environ['OPENCV_LOG_LEVEL'] = 'ERROR'
os.environ['OPENCV_VIDEOIO_DEBUG'] = '0'

import logging
import logging.handlers
import sys
from pathlib import Path

import uvicorn
import yaml


def load_log_config() -> dict:
    """Load logging configuration from config file before full config module"""
    defaults = {
        'file': './logs/nvr.log',
        'level': 'INFO',
        'max_size_mb': 10,
        'backup_count': 5
    }

    config_path = Path('config/config.yaml')
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
                if config and 'logging' in config:
                    log_config = config['logging']
                    return {
                        'file': log_config.get('file', defaults['file']),
                        'level': log_config.get('level', defaults['level']),
                        'max_size_mb': log_config.get('max_size_mb', defaults['max_size_mb']),
                        'backup_count': log_config.get('backup_count', defaults['backup_count'])
                    }
        except Exception:
            pass  # Use defaults if config can't be read

    return defaults


# Load logging configuration
log_config = load_log_config()

# Ensure log directory exists
log_path = Path(log_config['file'])
log_path.parent.mkdir(parents=True, exist_ok=True)

# Setup logging with rotation
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Rotating file handler
file_handler = logging.handlers.RotatingFileHandler(
    log_config['file'],
    maxBytes=log_config['max_size_mb'] * 1024 * 1024,
    backupCount=log_config['backup_count']
)
file_handler.setFormatter(log_formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

# Get log level
log_level = getattr(logging, log_config['level'].upper(), logging.INFO)

# Configure root logger
logging.basicConfig(
    level=log_level,
    handlers=[console_handler, file_handler]
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("SF-NVR - Network Video Recorder")
    logger.info("=" * 60)
    logger.info(f"Log file: {log_config['file']} (max {log_config['max_size_mb']}MB x {log_config['backup_count']} backups)")

    # Ensure config directory exists and check for config file
    Path("config").mkdir(exist_ok=True)

    if not Path("config/config.yaml").exists():
        logger.error("Configuration file not found: config/config.yaml")
        logger.info("Please create a configuration file based on the example")
        sys.exit(1)

    # Check for .env file
    if not Path(".env").exists():
        logger.warning(".env file not found - using defaults")
        logger.info("Copy .env.example to .env and configure as needed")

    # Start web server
    logger.info("Starting web server...")

    from nvr.core.config import config

    # Clean up cached transcoded files on startup (saves disk space)
    storage_path = config.storage_path
    transcode_cache = storage_path / ".transcoded"
    if transcode_cache.exists():
        import shutil
        try:
            file_count = len(list(transcode_cache.glob("*.mp4")))
            shutil.rmtree(transcode_cache)
            logger.info(f"Cleaned up {file_count} cached transcoded files")
        except Exception as e:
            logger.warning(f"Failed to clean transcoded cache: {e}")

    # Ensure storage directory exists
    storage_path.mkdir(parents=True, exist_ok=True)

    host = config.get('web.host', '0.0.0.0')
    port = config.get('web.port', 8080)

    logger.info(f"Web interface will be available at: http://{host}:{port}")
    logger.info("Press Ctrl+C to stop")

    # Check if we're in development mode (set DEV_MODE=1 in environment)
    dev_mode = os.getenv('DEV_MODE', '0') == '1'

    if dev_mode:
        logger.info("🔧 Development mode: Auto-reload enabled")

    # Configure uvicorn
    # IMPORTANT: Must use single worker because recorders capture frames in memory
    # and those frames need to be accessible to the same process handling HTTP requests
    workers = 1
    logger.info("Running in single-worker mode (required for video streaming)")

    uvicorn_config = uvicorn.Config(
        "nvr.web.api:app",
        host=host,
        port=port,
        log_level="info",
        access_log=False,
        timeout_graceful_shutdown=0,  # Force immediate shutdown
        reload=dev_mode,  # Enable auto-reload in dev mode
        reload_dirs=["nvr"] if dev_mode else None,  # Watch nvr directory
        workers=workers,  # Multiple workers for better performance
        backlog=2048,  # Increase connection backlog
        timeout_keep_alive=5  # Keep connections alive for better performance
    )
    server = uvicorn.Server(uvicorn_config)
    server.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)