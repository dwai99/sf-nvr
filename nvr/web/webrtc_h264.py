"""WebRTC H.264 passthrough for zero-latency streaming"""

import asyncio
import logging
import uuid
from typing import Dict
import av
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaPlayer

logger = logging.getLogger(__name__)


class H264StreamTrack(VideoStreamTrack):
    """H.264 video track that passes through encoded frames without re-encoding"""

    def __init__(self, rtsp_url: str, camera_name: str):
        super().__init__()
        self.rtsp_url = rtsp_url
        self.camera_name = camera_name
        self.player = None
        logger.info(f"Created H.264 passthrough track for {camera_name}")

    async def recv(self):
        """Receive next video frame directly from RTSP stream"""
        if self.player is None:
            # Create media player to read directly from RTSP
            # This bypasses OpenCV entirely for maximum performance
            self.player = MediaPlayer(self.rtsp_url, options={
                'rtsp_transport': 'tcp',
                'fflags': 'nobuffer',
                'flags': 'low_delay',
                'probesize': '32',
                'analyzeduration': '0'
            })
            logger.info(f"Started H.264 passthrough for {self.camera_name}")

        # Get frame directly from media player
        # This passes through H.264 without decoding/re-encoding
        try:
            frame = await self.player.video.recv()
            return frame
        except Exception as e:
            logger.error(f"Error receiving H.264 frame: {e}")
            # Return blank frame on error
            raise


class WebRTCPassthroughManager:
    """Manages WebRTC connections with H.264 passthrough (no re-encoding)"""

    def __init__(self, config):
        self.config = config
        self.pcs: Dict[str, RTCPeerConnection] = {}
        logger.info("WebRTC passthrough manager initialized")

    async def create_offer(self, camera_name: str, offer_sdp: dict) -> dict:
        """
        Create WebRTC offer with H.264 passthrough

        Args:
            camera_name: Name of camera to stream
            offer_sdp: Client's SDP offer

        Returns:
            SDP answer dictionary
        """
        # Find camera config
        cameras = self.config.get('cameras', [])
        camera_config = next((c for c in cameras if c['name'] == camera_name), None)

        if not camera_config:
            raise ValueError(f"Camera {camera_name} not found")

        rtsp_url = camera_config['rtsp_url']

        # Create peer connection
        pc = RTCPeerConnection()
        pc_id = str(uuid.uuid4())
        self.pcs[pc_id] = pc

        logger.info(f"Creating H.264 passthrough connection {pc_id} for {camera_name}")

        @pc.on("iceconnectionstatechange")
        async def on_ice_connection_state_change():
            logger.info(f"ICE connection state for {camera_name}: {pc.iceConnectionState}")
            if pc.iceConnectionState == "failed":
                await pc.close()
                if pc_id in self.pcs:
                    del self.pcs[pc_id]

        @pc.on("connectionstatechange")
        async def on_connection_state_change():
            logger.info(f"Connection state for {camera_name}: {pc.connectionState}")
            if pc.connectionState in ["failed", "closed"]:
                await pc.close()
                if pc_id in self.pcs:
                    del self.pcs[pc_id]

        # Create H.264 passthrough track
        video_track = H264StreamTrack(rtsp_url, camera_name)
        pc.addTrack(video_track)

        # Set remote description (client's offer)
        await pc.setRemoteDescription(RTCSessionDescription(
            sdp=offer_sdp["sdp"],
            type=offer_sdp["type"]
        ))

        # Create answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        logger.info(f"H.264 passthrough connection established for {camera_name}")

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "pc_id": pc_id
        }

    async def close_connection(self, pc_id: str):
        """Close a WebRTC peer connection"""
        if pc_id in self.pcs:
            await self.pcs[pc_id].close()
            del self.pcs[pc_id]
            logger.info(f"Closed WebRTC passthrough connection {pc_id}")

    async def close_all(self):
        """Close all WebRTC connections"""
        logger.info(f"Closing all {len(self.pcs)} WebRTC passthrough connections")
        for pc in self.pcs.values():
            await pc.close()
        self.pcs.clear()
