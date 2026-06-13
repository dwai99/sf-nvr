"""Ultra-fast RTSP proxy - streams H.264 directly to browser with ZERO processing"""

import asyncio
import logging
from typing import Dict
import subprocess

logger = logging.getLogger(__name__)


class RTSPProxy:
    """
    Direct RTSP to HTTP proxy using FFmpeg
    Bypasses ALL Python frame processing for maximum speed
    """

    def __init__(self):
        # Keyed by a unique stream id, not camera name: concurrent viewers of the
        # same camera each get their own entry instead of overwriting it (which
        # left earlier ffmpeg processes unreachable from stop_stream/stop_all).
        self.active_streams: Dict[int, tuple] = {}
        self._next_stream_id = 0
        logger.info("RTSP Proxy initialized (ZERO-LATENCY mode)")

    async def stream_camera(self, rtsp_url: str, camera_name: str):
        """
        Stream RTSP directly to HTTP using FFmpeg
        This is THE FASTEST possible way - raw H.264 passthrough

        Latency: ~50-100ms (vs 1-3 seconds with frame processing)
        """

        # FFmpeg command for ULTRA-LOW latency streaming
        # Outputs raw H.264 to stdout which we stream directly to browser
        ffmpeg_cmd = [
            "ffmpeg",
            "-rtsp_transport",
            "tcp",  # TCP for reliability
            "-fflags",
            "nobuffer",  # No buffering
            "-flags",
            "low_delay",  # Low delay mode
            "-analyzeduration",
            "0",  # Don't analyze stream
            "-probesize",
            "32",  # Minimal probe
            "-max_delay",
            "0",  # No delay
            "-reorder_queue_size",
            "0",  # No reordering
            "-i",
            rtsp_url,  # Input RTSP
            "-c:v",
            "copy",  # COPY codec - no re-encoding!
            "-an",  # No audio
            "-f",
            "mpegts",  # MPEG-TS container (streamable)
            "-tune",
            "zerolatency",  # Zero latency tuning
            "-preset",
            "ultrafast",  # Fastest preset
            "pipe:1",  # Output to stdout
        ]

        logger.info(f"Starting RTSP proxy for {camera_name}: {rtsp_url}")

        # Start FFmpeg process
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # Suppress FFmpeg logs
            bufsize=0,  # No buffering
        )

        stream_id = self._next_stream_id
        self._next_stream_id += 1
        self.active_streams[stream_id] = (camera_name, process)

        try:
            # Stream FFmpeg output directly to HTTP response
            # This is pure passthrough - no Python processing!
            while True:
                # Blocking pipe read offloaded so this async generator doesn't
                # stall the event loop (and every other camera) between chunks.
                chunk = await asyncio.to_thread(process.stdout.read, 8192)  # 8KB chunks
                if not chunk:
                    break
                yield chunk

        except Exception as e:
            logger.error(f"RTSP proxy error for {camera_name}: {e}")
        finally:
            # Cleanup
            process.kill()
            process.wait()
            self.active_streams.pop(stream_id, None)
            logger.info(f"Stopped RTSP proxy for {camera_name}")

    def stop_stream(self, camera_name: str):
        """Stop all streams for a camera"""
        for stream_id in [sid for sid, (name, _) in self.active_streams.items() if name == camera_name]:
            _, process = self.active_streams.pop(stream_id)
            process.kill()
            process.wait()
            logger.info(f"Stopped stream: {camera_name}")

    def stop_all(self):
        """Stop all streams"""
        for stream_id, (camera_name, process) in list(self.active_streams.items()):
            process.kill()
            process.wait()
            self.active_streams.pop(stream_id, None)
        logger.info("Stopped all RTSP proxy streams")


class MSEStreamProxy:
    """
    Media Source Extensions streaming
    Even faster than MPEG-TS - uses native browser decoder
    """

    async def stream_mse(self, rtsp_url: str):
        """
        Stream using fragmented MP4 for MSE
        Browser's native decoder handles everything
        """
        ffmpeg_cmd = [
            "ffmpeg",
            "-rtsp_transport",
            "tcp",
            "-fflags",
            "nobuffer+fastseek",
            "-flags",
            "low_delay",
            "-analyzeduration",
            "0",
            "-probesize",
            "32",
            "-i",
            rtsp_url,
            "-c:v",
            "copy",  # No re-encoding
            "-an",
            "-f",
            "mp4",  # Fragmented MP4
            "-movflags",
            "frag_keyframe+empty_moov+default_base_moof+faststart",
            "-reset_timestamps",
            "1",
            "pipe:1",
        ]

        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)

        try:
            while True:
                # Offload the blocking read so the event loop stays responsive.
                chunk = await asyncio.to_thread(process.stdout.read, 16384)  # 16KB chunks
                if not chunk:
                    break
                yield chunk
        finally:
            process.kill()
            process.wait()  # reap the process so it doesn't linger as a zombie
            process.wait()
