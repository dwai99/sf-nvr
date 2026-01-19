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
import sys
from pathlib import Path

import uvicorn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('nvr.log')
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("SF-NVR - Network Video Recorder")
    logger.info("=" * 60)

    # Ensure required directories exist
    Path("recordings").mkdir(exist_ok=True)
    Path("config").mkdir(exist_ok=True)

    # Check for config file
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

    host = config.get('web.host', '0.0.0.0')
    port = config.get('web.port', 8080)

    logger.info(f"Web interface will be available at: http://{host}:{port}")
    logger.info("Press Ctrl+C to stop")

    # Check if we're in development mode (set DEV_MODE=1 in environment)
    dev_mode = os.getenv('DEV_MODE', '0') == '1'

    if dev_mode:
        logger.info("🔧 Development mode: Auto-reload enabled")

    # Configure uvicorn with performance optimizations
    import multiprocessing

    # Use multiple workers in production for better performance
    workers = 1 if dev_mode else multiprocessing.cpu_count()

    if workers > 1:
        logger.info(f"🚀 Performance mode: Running with {workers} worker processes")

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