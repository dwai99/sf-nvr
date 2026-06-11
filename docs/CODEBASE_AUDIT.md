# Codebase Audit & Backlog

Generated 2026-06-11 from a full read-only audit (dead code, performance, robustness, features).
Items are roughly prioritized. `[x]` = done, `[ ]` = open.

## Done in this pass
- [x] **Dead code removed** — 32 unused imports, 3 unused locals, 3 placeholder f-strings;
  unused functions (recording-mode preset helpers, `run_segment_repair`, `clear_cache`,
  `check_all_profile_g_support`, `draw_detections`, `migrate_camera_ids`, `TimeRangeRequest`),
  dead JS helpers in `ui-utils.js`, and `templates/index.html.backup`. `nvr/` formatted with Black.
- [x] **Disk-full deadlock** — emergency cleanup now has an absolute-floor tier
  (`storage.absolute_min_free_gb`, default 2GB) that overrides `retention_days` and deletes
  oldest-first rather than letting the disk fill and silently stop recording. Raises
  `STORAGE_CRITICAL`. (`nvr/web/api.py` `disk_monitor_task`)
- [x] **Event-loop blocking** — wrapped blocking ffmpeg/pipe calls in `asyncio.to_thread`:
  speed-processing and timelapse `subprocess.run` (`playback_api.py`), and the two async-generator
  pipe reads in `rtsp_proxy.py`. Also reap the MSE ffmpeg process (`kill()` → `wait()`).

## Performance — open
- [ ] **MJPEG live path re-encodes per viewer on the loop** (`api.py` ~`/live`): decode→resize→
  imencode runs on the event loop and re-runs motion detection per viewer. Offload to a thread and
  cache one encode per (quality); reuse the motion monitor's latest result.
- [ ] **Recorder JPEG-encodes every frame 24/7** even with no live viewers (`recorder.py` `_record_frames`).
  Gate encoding on an actual consumer / throttle to ~10fps; drop the redundant `bytes(... .tobytes())` copy.
- [ ] **SQLite connection churn** (`playback_db.py` `_get_connection`): opens a new connection and
  re-issues `PRAGMA journal_mode=WAL` on every query. Pool/cache connections; set PRAGMAs once.
- [ ] **`OR camera_name` defeats indexes** (`playback_db.py` range queries): `WHERE (camera_id=? OR
  camera_name=?)` can't use either index. Query by `camera_id`, or UNION two indexed lookups.
- [ ] **Cleanup walks the 926GB volume** with `rglob('*.mp4')` (`recorder.py`, `storage_manager.py`)
  instead of querying the `recording_segments` table it already maintains.
- [ ] **Cache storage-stats / recordings listings** (short TTL); they're polled by the UI and re-scan.
- [ ] **Share one upstream ffmpeg per camera** for live viewers (`webrtc_h264.py`, `rtsp_proxy.py`) —
  today each viewer spawns its own camera connection + ffmpeg.
- [ ] **`psutil.cpu_percent(interval=0.1)`** blocks 100ms per system-stats poll (`api.py`); use `interval=None`.

## Robustness — open
- [ ] **Camera-down alerts go nowhere by default** — only `LogAlertHandler` is always on; alerts are
  in-memory and lost on restart. Ship a default email/ntfy/Pushover handler + persist to SQLite.
- [ ] **Motion detection dead for cameras enabled after startup** (`api.py` `start_camera`): detector +
  `monitor_recorder` task are only created at startup. Register/teardown them in start/stop_camera.
- [ ] **`/api/config` replaces whole sub-dicts** (`settings_api.py` `update_config`): a partial POST can
  drop `storage_path` etc. or delete omitted cameras. Deep-merge or validate a full schema.
- [ ] **RTSP direct-proxy leaks ffmpeg on concurrent viewers** (`rtsp_proxy.py`): `active_streams` keyed
  by camera name overwrites without killing the prior process. Key by unique stream id.
- [ ] **`webrtc_passthrough.close_all()` not called on shutdown** (`api.py` shutdown) — leak on exit.
- [ ] **Lock-free transcoder singleton** (`transcoder.py` `get_transcoder`) called from recorder threads;
  guard with a lock. Transcode `queue.Queue()` is unbounded — bound it.
- [ ] **Per-camera start/stop has no lock** (`api.py`): concurrent calls can interleave state.
- [ ] **`cleanup_old_incomplete_segments` estimates duration from file size** (`playback_db.py`); prefer
  the ffprobe-based `repair_missing_end_times`.

## Features — open (value/effort)
- [ ] **Default alert delivery + persisted/acknowledgeable alerts** (high / S) — turns existing detection
  into notifications users actually receive.
- [ ] **Consolidated mobile-ready `/api/status` + token auth** (high / M) — for the planned Flutter app
  (`docs/MOBILE_APP_ROADMAP.md`); current `/health` omits per-camera write_failed/storage status.
- [ ] **Cross-camera motion/event search API + UI** (high / M) — schema/indexes already support it.
- [ ] **`/metrics` (Prometheus) or richer `/health`** (med / S) — per-camera fps/reconnects, transcode
  queue depth, disk %, active recorders (most values already on recorder objects).
- [ ] **Test coverage for thin/high-risk modules** (med / M) — `recording_modes`, `disk_manager`
  (the retention/disk-full path), `onvif_discovery`, `rtsp_proxy`, webrtc currently ~0 tests.
- [ ] **Structured (JSON) logging option** (med / S); **per-camera storage quotas** (low / M).

## Kept intentionally (not dead — for the planned mobile app)
- WebRTC subsystem (`webrtc_server.py`, `webrtc_h264.py`, `/api/webrtc/offer`, `webrtc-client.js`)
- Direct-RTSP / MSE proxy (`rtsp_proxy.py`, `/stream/direct`, `/stream/mse`)
- `config.py` camera accessors (`get_camera_by_id`, `get_camera_by_name`, etc.) — unused today,
  likely needed by the mobile API.
