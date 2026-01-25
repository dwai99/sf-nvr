# Mobile App Roadmap

## Overview

Future implementation of a custom mobile application for remote NVR access on iOS and Android.

## Target Users

- 3 users currently

## Recommended Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Framework** | Flutter | Single codebase for iOS and Android |
| **NAT Traversal** | Tailscale SDK | No firewall/port forwarding needed, free for small teams |
| **Video Playback** | HLS | Already supported by NVR transcoder |
| **Live Streaming** | WebRTC (future) | Low latency live view |

## Why Tailscale

- Free tier supports up to 100 devices (we have 3 users)
- Embeddable SDK for iOS/Android - no separate Tailscale app needed
- Handles all NAT traversal complexity
- End-to-end encrypted (WireGuard)
- Zero configuration for end users

## Features (Priority Order)

### Phase 1 - Core Functionality
- [ ] Live camera view (single and grid)
- [ ] Playback with timeline scrubbing
- [ ] Camera selection

### Phase 2 - Notifications
- [ ] Push notifications for motion/AI events
- [ ] Event thumbnails in notifications
- [ ] Quick view from notification

### Phase 3 - Enhanced Features
- [ ] Download clips to device
- [ ] Two-way audio (if cameras support)
- [ ] Widget for quick camera access
- [ ] Apple Watch / Wear OS companion

## Technical Notes

### Tailscale Integration

```dart
// Conceptual - Tailscale Flutter integration
// Tailscale provides native SDKs that can be wrapped
```

NVR server setup:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

App connects to NVR via Tailscale IP (e.g., `100.x.x.x`) or MagicDNS name.

### API Endpoints Needed

Current NVR API should work as-is:
- `GET /api/cameras` - list cameras
- `GET /api/playback/video/{camera}` - video stream
- `GET /api/recordings` - recording segments
- WebSocket for live updates (motion events, status)

### Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Cloudflare Tunnel | Browser-based, no app install | They terminate TLS |
| Own relay VPS | Full control | Bandwidth costs, maintenance |
| Pure WebRTC P2P | No relay costs | Complex, 10-15% NAT failure rate |

## Resources

- [Tailscale Mobile SDKs](https://tailscale.com/kb/1232/mobile-sdk)
- [Flutter Documentation](https://flutter.dev/docs)
- [flutter_webrtc package](https://pub.dev/packages/flutter_webrtc)

## Status

**Status:** Planned for future implementation
**Created:** 2026-01-24
