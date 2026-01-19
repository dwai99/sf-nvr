"""WebRTC server implementation for low-latency video streaming"""

import asyncio
import logging
import uuid
from typing import Dict, Optional
import av
import cv2
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay
from av import VideoFrame

logger = logging.getLogger(__name__)


class CameraVideoTrack(VideoStreamTrack):
    """Video track that reads from camera recorder's frame queue"""

    def __init__(self, recorder, camera_name: str):
        super().__init__()
        self.recorder = recorder
        self.camera_name = camera_name
        self.frame_count = 0
        # Cache last BGR frame and its RGB conversion to avoid redundant color conversions
        self.last_bgr_frame = None
        self.last_rgb_frame = None
        logger.info(f"Created WebRTC video track for {camera_name}")

    async def recv(self):
        """Receive next video frame"""
        pts, time_base = await self.next_timestamp()

        # Get latest frame from recorder
        frame = self.recorder.get_latest_frame()

        if frame is None:
            # Use cached frame if available, otherwise return blank
            if self.last_rgb_frame is not None:
                frame_rgb = self.last_rgb_frame
            else:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                frame_rgb = frame
        else:
            # Only convert if this is a new frame (not the same cached frame)
            if frame is not self.last_bgr_frame:
                # Convert BGR (OpenCV) to RGB (WebRTC expects RGB)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.last_bgr_frame = frame
                self.last_rgb_frame = frame_rgb
            else:
                # Reuse cached RGB conversion
                frame_rgb = self.last_rgb_frame

        # Create VideoFrame from numpy array
        video_frame = VideoFrame.from_ndarray(frame_rgb, format='rgb24')
        video_frame.pts = pts
        video_frame.time_base = time_base

        self.frame_count += 1

        # No delay needed - let WebRTC stream at maximum speed
        # The recorder's frame rate naturally limits delivery speed
        return video_frame


class WebRTCManager:
    """Manages WebRTC peer connections for camera streams"""

    def __init__(self, recorder_manager):
        self.recorder_manager = recorder_manager
        self.pcs: Dict[str, RTCPeerConnection] = {}
        self.relay = MediaRelay()
        logger.info("WebRTC manager initialized")

    async def create_offer(self, camera_name: str, offer_sdp: dict) -> dict:
        """
        Create WebRTC offer for a camera stream

        Args:
            camera_name: Name of camera to stream
            offer_sdp: Client's SDP offer

        Returns:
            SDP answer dictionary
        """
        # Get recorder for camera
        recorder = self.recorder_manager.get_recorder(camera_name)
        if not recorder:
            raise ValueError(f"Camera {camera_name} not found")

        # Create peer connection
        pc = RTCPeerConnection()
        pc_id = str(uuid.uuid4())
        self.pcs[pc_id] = pc

        logger.info(f"Creating WebRTC connection {pc_id} for {camera_name}")

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

        # Create video track
        video_track = CameraVideoTrack(recorder, camera_name)
        pc.addTrack(self.relay.subscribe(video_track))

        # Set remote description (client's offer)
        await pc.setRemoteDescription(RTCSessionDescription(
            sdp=offer_sdp["sdp"],
            type=offer_sdp["type"]
        ))

        # Create answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        logger.info(f"WebRTC connection established for {camera_name}")

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
            logger.info(f"Closed WebRTC connection {pc_id}")

    async def close_all(self):
        """Close all WebRTC connections"""
        logger.info(f"Closing all {len(self.pcs)} WebRTC connections")
        for pc in self.pcs.values():
            await pc.close()
        self.pcs.clear()
