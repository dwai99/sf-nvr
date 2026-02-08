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
            return;
        }

        this.isConnecting = true;
        const startTime = performance.now();

        try {
            // Create RTCPeerConnection
            // For local network, we don't need STUN/TURN servers - direct connection works
            const t0 = performance.now();
            this.peerConnection = new RTCPeerConnection({
                iceServers: [],  // Empty for local network - faster connection
                iceCandidatePoolSize: 0  // Don't pre-gather candidates
            });

            // Handle incoming video track
            this.peerConnection.ontrack = (event) => {
                const trackTime = performance.now() - startTime;
                if (this.videoElement) {
                    this.videoElement.srcObject = event.streams[0];
                    this.videoElement.play().catch(e => {
                        console.error('Error playing video:', e);
                    });
                }
            };

            // Handle ICE connection state changes
            this.peerConnection.oniceconnectionstatechange = () => {

                if (this.peerConnection.iceConnectionState === 'failed' ||
                    this.peerConnection.iceConnectionState === 'disconnected') {
                    this.handleDisconnect();
                } else if (this.peerConnection.iceConnectionState === 'connected') {
                    this.reconnectAttempts = 0;
                }
            };

            // Handle connection state changes
            this.peerConnection.onconnectionstatechange = () => {

                if (this.peerConnection.connectionState === 'failed' ||
                    this.peerConnection.connectionState === 'closed') {
                    this.handleDisconnect();
                }
            };

            // Add transceivers (receive-only)
            const t1 = performance.now();
            this.peerConnection.addTransceiver('video', { direction: 'recvonly' });

            // Create offer
            const t2 = performance.now();
            const offer = await this.peerConnection.createOffer();

            const t3 = performance.now();
            await this.peerConnection.setLocalDescription(offer);

            // For local network with no ICE servers, skip ICE gathering entirely
            // This saves 2 seconds of waiting

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
            this.pc_id = answer.pc_id;

            // Set remote description (server's answer)
            const t5 = performance.now();
            await this.peerConnection.setRemoteDescription(
                new RTCSessionDescription({
                    sdp: answer.sdp,
                    type: answer.type
                })
            );

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

        this.stop();

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);

            setTimeout(() => {
                this.start();
            }, delay);
        } else {
            console.error('Max reconnection attempts reached');
        }
    }

    stop() {

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
