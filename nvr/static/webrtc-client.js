/**
 * WebRTC Client for SF-NVR
 * Provides low-latency video streaming using WebRTC
 */

class WebRTCPlayer {
    constructor(cameraName, videoElement) {
        this.cameraName = cameraName;
        this.videoElement = videoElement;
        this.peerConnection = null;
        this.pc_id = null;
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    async start() {
        if (this.isConnecting || this.peerConnection) {
            console.log('WebRTC already connecting or connected');
            return;
        }

        this.isConnecting = true;
        const startTime = performance.now();
        console.log(`[WebRTC] Starting connection for camera: ${this.cameraName}`);

        try {
            // Create RTCPeerConnection
            // For local network, we don't need STUN/TURN servers - direct connection works
            const t0 = performance.now();
            this.peerConnection = new RTCPeerConnection({
                iceServers: [],  // Empty for local network - faster connection
                iceCandidatePoolSize: 0  // Don't pre-gather candidates
            });
            console.log(`[WebRTC] Peer connection created (${(performance.now() - t0).toFixed(0)}ms)`);

            // Handle incoming video track
            this.peerConnection.ontrack = (event) => {
                const trackTime = performance.now() - startTime;
                console.log(`[WebRTC] Received video track (${trackTime.toFixed(0)}ms from start)`);
                if (this.videoElement) {
                    this.videoElement.srcObject = event.streams[0];
                    this.videoElement.play().catch(e => {
                        console.error('Error playing video:', e);
                    });
                }
            };

            // Handle ICE connection state changes
            this.peerConnection.oniceconnectionstatechange = () => {
                console.log(`[WebRTC] ICE connection state: ${this.peerConnection.iceConnectionState}`);

                if (this.peerConnection.iceConnectionState === 'failed' ||
                    this.peerConnection.iceConnectionState === 'disconnected') {
                    this.handleDisconnect();
                } else if (this.peerConnection.iceConnectionState === 'connected') {
                    this.reconnectAttempts = 0;
                    console.log(`[WebRTC] Total connection time: ${(performance.now() - startTime).toFixed(0)}ms`);
                }
            };

            // Handle connection state changes
            this.peerConnection.onconnectionstatechange = () => {
                console.log(`[WebRTC] Connection state: ${this.peerConnection.connectionState}`);

                if (this.peerConnection.connectionState === 'failed' ||
                    this.peerConnection.connectionState === 'closed') {
                    this.handleDisconnect();
                }
            };

            // Add transceivers (receive-only)
            const t1 = performance.now();
            this.peerConnection.addTransceiver('video', { direction: 'recvonly' });
            console.log(`[WebRTC] Added transceiver (${(performance.now() - t1).toFixed(0)}ms)`);

            // Create offer
            const t2 = performance.now();
            const offer = await this.peerConnection.createOffer();
            console.log(`[WebRTC] Created offer (${(performance.now() - t2).toFixed(0)}ms)`);

            const t3 = performance.now();
            await this.peerConnection.setLocalDescription(offer);
            console.log(`[WebRTC] Set local description (${(performance.now() - t3).toFixed(0)}ms)`);

            // For local network with no ICE servers, skip ICE gathering entirely
            // This saves 2 seconds of waiting
            console.log('[WebRTC] Skipping ICE gathering (not needed for local network)');

            // Send offer to server
            const t4 = performance.now();
            const response = await fetch('/api/webrtc/offer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    camera_name: this.cameraName,
                    sdp: this.peerConnection.localDescription.sdp,
                    type: this.peerConnection.localDescription.type,
                    passthrough: false  // Disabled until server restart - set to true after restarting
                })
            });

            if (!response.ok) {
                throw new Error(`Server returned ${response.status}: ${await response.text()}`);
            }

            const answer = await response.json();
            console.log(`[WebRTC] Received server answer (${(performance.now() - t4).toFixed(0)}ms)`);
            this.pc_id = answer.pc_id;

            // Set remote description (server's answer)
            const t5 = performance.now();
            await this.peerConnection.setRemoteDescription(
                new RTCSessionDescription({
                    sdp: answer.sdp,
                    type: answer.type
                })
            );
            console.log(`[WebRTC] Set remote description (${(performance.now() - t5).toFixed(0)}ms)`);

            console.log(`[WebRTC] Connection established (total setup: ${(performance.now() - startTime).toFixed(0)}ms)`);
            this.isConnecting = false;

        } catch (error) {
            console.error('WebRTC error:', error);
            this.isConnecting = false;
            this.handleDisconnect();
        }
    }

    waitForICEGathering() {
        return new Promise((resolve) => {
            if (this.peerConnection.iceGatheringState === 'complete') {
                resolve();
            } else {
                const checkState = () => {
                    if (this.peerConnection.iceGatheringState === 'complete') {
                        this.peerConnection.removeEventListener('icegatheringstatechange', checkState);
                        resolve();
                    }
                };
                this.peerConnection.addEventListener('icegatheringstatechange', checkState);

                // Reduced timeout for faster connection - 2 seconds is enough for local network
                setTimeout(() => {
                    this.peerConnection.removeEventListener('icegatheringstatechange', checkState);
                    resolve();
                }, 2000);
            }
        });
    }

    handleDisconnect() {
        console.log('WebRTC disconnected, attempting to reconnect...');

        this.stop();

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
            console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

            setTimeout(() => {
                this.start();
            }, delay);
        } else {
            console.error('Max reconnection attempts reached');
        }
    }

    stop() {
        console.log('Stopping WebRTC connection');

        if (this.peerConnection) {
            this.peerConnection.close();
            this.peerConnection = null;
        }

        if (this.videoElement) {
            this.videoElement.srcObject = null;
        }

        this.pc_id = null;
        this.isConnecting = false;
    }
}

// Export for use in templates
window.WebRTCPlayer = WebRTCPlayer;
