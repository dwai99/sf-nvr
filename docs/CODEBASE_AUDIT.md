# Codebase Audit & Backlog

Generated 2026-06-11 from a full read-only audit (dead code, performance, robustness, features).
`[x]` = done, `[ ]` = deferred (with rationale at the bottom).

## Performance
- [x] **Dead code removed** — unused imports/locals/f-strings, unused functions, dead JS helpers,
  `index.html.backup`; `nvr/` formatted with Black (CI `black --check` passes).
- [x] **MJPEG live path re-encodes per viewer** — offloaded to a worker thread and shared via a
  per-recorder cache (`recorder.render_live_frame`); overlay reuses the monitor's boxes.
- [x] **Recorder JPEG-encodes every frame 24/7** — demand-gated (`JPEG_DEMAND_SECONDS`); motion uses
  the raw frame (`get_latest_raw_frame`); dropped the redundant byte copy.
- [x] **SQLite connection churn** — per-thread reused connection, PRAGMAs set once.
- [x] **Cache storage-stats** — `get_storage_stats` cached 30s (was two full scans per UI poll).
- [x] **psutil.cpu_percent** — `interval=None` (non-blocking) instead of a 100ms event-loop stall.
- [ ] **`OR camera_name` defeats indexes** — deferred.
- [ ] **Cleanup walks the volume via `rglob`** — partly addressed (single-pass walk already; orphan
  cleanup below handles untracked files). Full DB-driven rewrite deferred.
- [ ] **Share one upstream ffmpeg per camera** for live viewers — deferred.

## Robustness
- [x] **Disk-full deadlock** — absolute-floor tier (`storage.absolute_min_free_gb`) overrides retention.
- [x] **Event-loop blocking** — `asyncio.to_thread` around ffmpeg/pipe calls; MSE process reaped.
- [x] **Camera-down alerts go nowhere / lost on restart** — alerts persisted to SQLite, listable and
  acknowledgeable (`/api/alerts`), surfaced in `/api/status`, pruned after 30 days.
- [x] **Motion detection dead for cameras enabled after startup** — `MotionMonitor.ensure_monitoring`
  registers a per-camera task in `start_camera`.
- [x] **`/api/config` replaces whole sub-dicts** — now merges each section over stored values.
- [x] **RTSP direct-proxy leaks ffmpeg on concurrent viewers** — keyed by unique stream id.
- [x] **`webrtc_passthrough.close_all()` not called on shutdown** — now awaited.
- [x] **Lock-free transcoder singleton / unbounded queue** — lock + bounded queue (drop+warn when full).
- [x] **`cleanup_old_incomplete_segments` size estimate** — uses real ffprobe duration; drops
  unprobeable/truncated rows.
- [ ] **Per-camera start/stop lock** — deferred.

## Features
- [x] **Persisted/acknowledgeable alerts** (see Robustness).
- [x] **Consolidated `/api/status`** — per-camera health + storage + transcode backlog + system + open
  alert count, one call for the mobile app.
- [x] **`/metrics` (Prometheus)** — per-camera recording/write_failed/reconnects + disk + queue depth.
- [x] **Cross-camera motion/event search** — `GET /api/playback/motion-events/search` (camera /
  intensity / type filters + paging).
- [x] **Structured (JSON) logging** — opt-in via `logging.json: true`.
- [x] **Orphaned-file cleanup** (bonus, user-requested) — `GET /api/storage/orphans` and a maintenance
  step; dry-run by default, real deletion behind `storage.orphan_cleanup_enabled`. Safety rails:
  min-age, hidden/cache dirs, `_h264` variants, storage-mounted check.
- [x] **Tests** for the above (alerts, search, orphan cleanup) — `tests/unit/test_audit_additions.py`.
- [ ] **Token auth for the mobile app** — deferred (needs a scheme decision; HTTP Basic exists today).
- [ ] **Per-camera storage quotas** — deferred (lower value; retention-logic change).

## Deferred — rationale
- **`OR camera_name` index rewrite**: 9 query sites; a correct fix needs UNION-of-indexed-lookups with
  ordering/dedup care around the camera_id↔camera_name migration. Medium gain (queries are already
  bounded by the time index), high regression risk — not worth it in this pass.
- **Cleanup via DB instead of `rglob`**: DB-driven cleanup would miss on-disk files with no row
  (exactly the orphans the new cleanup targets), so the filesystem walk is still needed; the walk is
  already single-pass. A hybrid rewrite is larger than its remaining payoff here.
- **Share one upstream ffmpeg per camera**: significant rework of the WebRTC/RTSP streaming path, which
  is currently used by the (not-yet-active) mobile subsystem. Revisit when the mobile app lands.
- **Per-camera start/stop lock**: low severity (≤3 users; `recorder.start()` already guards the unsafe
  use-after-free). The fix re-indents three large handlers — churn/risk outweighs the benefit now.
- **Token auth / per-camera quotas**: product decisions (auth scheme; quota policy) — surface to owner.

## Kept intentionally (not dead — for the planned mobile app)
- WebRTC subsystem, direct-RTSP/MSE proxy, and `config.py` camera accessors.
