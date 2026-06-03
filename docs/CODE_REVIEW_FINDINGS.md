# NVR Code Review — Findings

Comprehensive review of ~21k lines (10k Python, 11.5k templates/JS) conducted 2026-06-02 across 6 subsystems. Findings are grouped by area, with severity, `file:line`, the problem, and the fix. Status legend:

- ✅ **FIXED** — addressed in the 2026-06-02 session (see [Changelog](#changelog-2026-06-02)).
- ⬜ **OPEN** — not yet addressed.

Severity: 🔴 Critical · 🟠 High · 🟡 Medium · ⚪ Low.

> Methodology note: every concrete runtime claim below was verified against source (9/9 spot-checks confirmed). Line numbers drift as the code changes — search by symbol if a line doesn't match.

---

## Top priorities (cross-cutting, deduplicated)

| # | Sev | Status | Issue | Where |
|---|-----|--------|-------|-------|
| 1 | 🔴 | ✅* | No authentication on any endpoint (opt-in HTTP Basic added; CORS `*`/bind `0.0.0.0` unchanged — acceptable on isolated LAN) | `api.py` |
| 2 | 🔴 | ✅ | Camera credentials (rtsp_url w/ password) sent to every browser | `api.py:565`, `settings.html` |
| 3 | 🔴 | ✅ | `config.save_config()` doesn't exist → settings saves 500 | `settings_api.py:199,273` |
| 4 | 🔴 | ✅ | `get_camera_health` NameError → endpoint always 500s | `api.py:621` |
| 5 | 🔴 | ✅ | `live_stream` NameError on motion path | `api.py:934` |
| 6 | 🔴 | ✅ | `export_clip` misbinds positional args → export always 500s | `playback_api.py:1088` |
| 7 | 🔴 | ✅ | Health & alerts ignore `write_failed` (silent-outage blind spot) | `api.py`, `alert_system.py` |
| 8 | 🔴 | ✅ | `write_failed` missed mid-segment write loss | `recorder.py` |
| 9 | 🔴 | ✅ | `config.storage_path` recreates mountpoint on every access | `config.py` |
| 10 | 🔴 | ✅* | DiskManager ignores retention / deletes active segment / spins on EPERM (*engine consolidation still open) | `storage_manager.py`, `disk_manager.py` |

---

## Recording pipeline (`recorder.py`, `transcoder.py`, `motion.py`, `recording_modes.py`)

### 🔴 Critical
- ✅ **Mid-segment silent write loss.** `write_failed` was `self.writer is None`, only set when a *new* segment fails to open. A volume going read-only mid-segment leaves `writer` non-None while `write()` silently no-ops → up to 5 min of green "REC" with zero bytes. **Fixed:** added `_check_segment_growth()` sampling the segment file size every ~20s; flags `write_failed` if it stops growing or vanishes.
- ✅ **Motion detection blocked the event loop.** `motion.py` ran `cv2.imdecode` + full contour detection synchronously on the asyncio loop, every frame × every camera, re-decoding the same cached frame every 10ms. **Fixed:** `monitor_recorder` now runs decode+detection in a worker thread (`asyncio.to_thread`), skips frames already processed (identity check on the cached buffer), and polls at 0.2s. The shared `MotionDetector` got a lock so the live-view overlay and the motion thread can call `process_frame` concurrently. Verified live: API ~2ms avg under load, live overlay still streams.

### 🟠 High
- ✅ **DST / clock-step corruption.** **Fixed:** segment duration now uses `time.monotonic()` clamped to `>= 0` (immune to DST/NTP backward steps); `_start_new_segment` uniquifies the filename if it already exists, so a repeated boundary (DST fall-back or restart-within-boundary) no longer overwrites the prior segment's file or its DB row.
- ✅ **Non-atomic transcode replace.** `transcoder.py` did `unlink()` then `rename()`; a crash/IO error between them destroyed the segment. **Fixed:** single atomic `os.replace(transcoded, source)`.
- ⬜ **No transcode queue de-dup.** `transcoder.py:68-93` — same file can be queued twice and transcoded by two workers concurrently to the same path. **Fix:** track in-flight paths in a lock-guarded set.
- ✅ **In-place start/stop race.** **Fixed:** `start()` now refuses (after a 2s join) while the prior capture thread is still alive, so a toggle can't spawn a second capture loop; `stop()` only calls `_cleanup()` if the thread has exited, otherwise defers to the thread's own `finally` — no more releasing `VideoCapture`/`VideoWriter` out from under a live `read()`.
- ✅ **Per-frame exception kills capture session.** **Fixed:** the per-frame body is wrapped in try/except — a single bad/corrupt frame (common on weak-signal cameras like Alley) is logged (rate-limited) and skipped instead of tearing down the capture session and forcing a full RTSP reconnect.

### 🟡 Medium
- ✅ **Disconnect orphans open segment.** `_cleanup` released the writer but never called `_close_current_segment` → DB row stuck `end_time=NULL`, never transcoded. **Fixed:** `_cleanup` now finalizes + queues the open segment (idempotent); also fires on clean stop. Especially relevant for flaky cameras (e.g. Alley's weak wifi) that reconnect often.
- ⬜ **`buffered_frames` / `pre_motion_seconds` unimplemented.** `recorder.py:73` declared, never used → motion clips start late; documented knob silently does nothing.
- ⬜ **`motion_timeout` config unused** (`recording_modes.py:53`); motion post-roll logic split between layers.
- ⬜ **`23:59` schedule gap.** `recording_modes.py:253-257` inclusive end drops ~59s before midnight every day for "24/7" presets. **Fix:** `end=time(23,59,59)` or half-open interval.
- ⬜ **`frame_lock` held across queue ops** (`recorder.py:304`) contends with every live-view/motion reader. **Fix:** rely on `Queue`'s own locking.
- ⬜ **MOG2 background subtractor built but never used** (`motion.py:41`) — dead per-camera memory; `sensitivity` overloaded.
- ⬜ **Motion timing uses naive `datetime.now()`** (`motion.py:130`) — backward clock step makes a motion event never end.

### ⚪ Low
- ⬜ Dead `import gc` + no-op per-frame `del` (`recorder.py:14,317`).
- ⬜ `_is_frame_corrupted` dead code (`recorder.py:548-585`).
- ⬜ `cleanup_old_recordings` deletes files but not DB rows (`recorder.py:740`).
- ⬜ Deprecated `stimeout` in RTSP options (`recorder.py:18`).
- ⬜ Transcoder `priority=True` accepted but ignored (`transcoder.py:87`).
- ⬜ `log_motion_event()` double-counts first motion frame (`motion.py:137`).

---

## Playback backend (`playback_db.py`, `playback_api.py`)

### 🔴 Critical
- ✅ **`export_clip` broken.** `playback_api.py:1088` called `stream_video_segment(request.camera_id, request.start_time, request.end_time)` but the signature is `(camera_id, request, background_tasks, ...)` — the string bound to `request`, `.headers.get()` threw, export always 500'd. **Fixed:** call with keyword args + real injected `Request`/`BackgroundTasks`, and `except HTTPException: raise` so 404/202 aren't masked as 500. Verified live (HTTP 200, `video/mp4`). The frontend's actual export path (`GET /api/playback/video` via `performExport`) was also hardened — see frontend section.

### 🟠 High
- ✅ **Synchronous transcode on request path.** **Fixed:** `ffprobe`/`ffmpeg` now run via `asyncio.to_thread` with timeouts (15s/180s), so playback of a legacy mp4v segment no longer freezes the server; a per-output `asyncio.Lock` serializes concurrent requests for the same file, and the transcode writes to a temp file then `os.replace`s atomically (never serves a partial). Verified: video serves (206), API ~8ms during.
- ✅ **H.264 transcode cache has no freshness check** — **Fixed:** `_cache_is_fresh()` compares the cached transcode's mtime to the source (applied to both the background-transcoded and on-demand paths).
- ⬜ **Range requests non-conformant.** `playback_api.py:136-169` — no `416` for unsatisfiable ranges (negative-length empty 206), `ValueError` 500 on malformed header, mis-parses suffix ranges (`bytes=-500`), missing Content-Length on 206. **Fix:** use Starlette `FileResponse` for simple cases (fixes blocking I/O too).
- ⬜ **`/sd-card-gaps` serial blocking ONVIF calls per camera** (`playback_api.py:1349`) — one slow camera hangs the whole response; self-DoS. **Fix:** `asyncio.gather` + per-camera `wait_for`.
- ✅ **SQLite has no WAL / busy_timeout** (`playback_db.py`) — connection-per-call with defaults → `database is locked` under record+playback. **Fixed:** `_get_connection` sets `journal_mode=WAL`, `busy_timeout=5000`, `timeout=30`. Verified WAL active live.
- ⬜ **Long maintenance txns wrap ffprobe/file scans** (`playback_db.py:1071`) — hold write lock for minutes. **Fix:** do slow work outside the transaction.

### 🟡 Medium
- ⬜ **Path-traversal check prefix-bypassable.** `playback_api.py:707` uses `str.startswith` on resolved paths → `/Volumes/Video Storage_backup/...` passes. **Fix:** `Path.is_relative_to` or compare with trailing `os.sep`; restrict to `.mp4`.
- ✅ **camera_id/camera_name fallback dropped legacy rows.** **Fixed:** `get_segments_in_range` and `get_motion_events_in_range` now use a single `(camera_id = ? OR camera_name = ?)` query, so mixed-keying cameras no longer silently lose recordings/motion events.
- ⬜ **Inconsistent overlap operators** between single- vs all-camera range queries (`playback_db.py:422` vs `472`) → boundary segments differ between views.
- ⬜ **Blocking file-iterator generators** (`playback_api.py:151`) block the loop on slow storage.
- ⬜ **Redundant `exists()`/`stat()` per segment** (`playback_api.py:507-547`) — hundreds of syscalls on full-day requests.
- ⬜ **Fallback loads all segments** on a range miss (`playback_api.py:476`). **Fix:** `get_next_segment_after(...) LIMIT 1`.
- ⬜ **Motion bucketing `strftime('%s')` → epoch 0** for unparseable timestamps (`playback_db.py:580`).
- ⬜ **`get_storage_stats` full-table scan + groups by name not id** (`playback_db.py:625`).
- ⬜ **SD streaming 10MB pipe buffer + process leak** if client never connects (`playback_api.py:806`).

### ⚪ Low
- ⬜ `delete_segment_by_path` unescaped LIKE wildcards (`playback_db.py:763`).
- ⬜ `fromisoformat` assumes str without guard (`playback_db.py:726,1110`).
- ⬜ `INSERT OR REPLACE` changes row id / resets columns (`playback_db.py:357`).
- ⬜ Timelapse `end_time` boundary + validation (`playback_api.py:953`).
- ⬜ SD times tz-aware vs naive-local gap math (`playback_api.py:1430`).

---

## Web API core (`api.py`, `recording_api.py`, `settings_api.py`, `main.py`)

### 🔴 Critical
- ✅* **No authentication anywhere.** No `Depends`/auth across `nvr/web/*.py`; `CORSMiddleware(allow_origins=["*"])`; bind `0.0.0.0`. **Fixed (opt-in):** added HTTP Basic auth middleware (`basic_auth_middleware` + `_check_basic_auth`), enabled when `web.auth_password` is set in config. Runs only for HTTP (WebSockets stay open on the trusted LAN by design). CORS `*` and `0.0.0.0` bind left as-is — acceptable for this deployment (isolated network: only cameras + NVR), and Basic auth means browsers won't send creds cross-origin anyway. *Deployment note: keep port 8080 off any internet port-forward.*
- ✅ **`get_camera_health` NameError** (`api.py:621`) — `camera_name` unbound → always 500. **Fixed:** use `recorder.camera_name`; also added `write_failed`/`actively_writing` + `write_failed` status.
- ✅ **`live_stream` NameError** (`api.py:934`) — `camera_name` unbound on the motion path → default MJPEG stream aborts mid-response. **Fixed:** bind `camera_name = recorder.camera_name`.
- ✅ **`settings_api.save_config()` missing** (`settings_api.py:199,273`) — motion & recording settings saves 500 and leave memory/disk divergent. **Fixed:** `config.save()`.

### 🟠 High
- ⬜ **Blocking cv2 in `live_stream` generator** (`api.py:917`) — decode/resize/motion/encode on the event loop, single worker → stalls all requests. **Fix:** `asyncio.to_thread`.
- ⬜ **Blocking `process.stdout.read()` in RTSP/MSE proxies** (`rtsp_proxy.py:67,135`) — no `await` between reads; ffmpeg subprocess leaks on disconnect. **Fix:** async subprocess; track+kill processes.
- ⬜ **WebSockets never `close()` on generic error** (`api.py:1128,1225`).
- ⬜ **Health-monitor runs a second event loop in a thread** (`api.py:194`) calling async handlers + touching main-loop objects. **Fix:** `asyncio.create_task` on the main loop.
- ⬜ **`POST /api/config` no validation, replaces whole sections** (`settings_api.py:45`) — one bad PATCH can drop `storage_path`. **Fix:** typed models + deep merge.

### 🟡 Medium
- ⬜ Deprecated `@app.on_event`; background tasks never cancelled on shutdown (`api.py:70,402`).
- ⬜ Control endpoints return 200 with `{success:false}` instead of error codes (`api.py:757,795,...`).
- ⬜ Per-request full directory walk + blocking `stat()`, no pagination (`api.py:1000,1078`).
- ⬜ `psutil.cpu_percent(interval=1)` blocks loop 1s (`settings_api.py:117`; `api.py:1469`).
- ⬜ None-deref when managers not yet initialized; inconsistent 503 guarding (`api.py`).
- ⬜ Cleanup runs blocking deletes in async tasks (`api.py:432,465`).
- ⬜ `recording_api` generic `except Exception` masks intended 503/400 (`recording_api.py:91,127,205,247`).

### ⚪ Low
- ⬜ `discover_cameras(ip_range=None)` + bare `except:` (`api.py:693,715`).
- ⬜ Startup `queue_mp4v_files_async` spawns ffprobe per file across archive (`api.py:90`).
- ⬜ `debug_camera` swallows errors into 200, leaks internals (`api.py:593`).
- ⬜ `main.py` stale "multiple workers" comment (`main.py:153`); startup transcode-cache wipe (`main.py:113`).

---

## Storage & lifecycle (`storage_manager.py`, `disk_manager.py`, `sd_card_manager.py`, `cache_cleaner.py`, `db_maintenance.py`, `alert_system.py`, `config.py`)

### 🔴 Critical
- ✅ **No write-failure / unwritable-storage detection (root cause of the Jan outage).** Recorder knew (`write_failed`) and `/api/cameras` exposed it, but `get_all_cameras_health` and `alert_system.check_storage` ignored it → "storage low" fired forever while nothing recorded. **Fixed:** health status now includes `write_failed`; added `AlertType.CAMERA_WRITE_FAILED` + `STORAGE_UNWRITABLE`; `config.is_storage_writable()` probe wired into the health loop.
- ✅ **`config.storage_path` recreates the mountpoint on every access** (`config.py`) — on unmount, silently recreates the dir on the boot drive and writes recordings there. **Fixed:** create once (`_storage_initialized`); never recreate after init.
- ✅ **Cleanup deletes the actively-writing segment.** Both engines now accept `protected_paths` from `RecorderManager.get_active_segment_paths()` and skip active segments; `_cleanup_empty_dirs` skips active camera dirs + hidden cache dirs. *(Single shared cleanup lock / engine consolidation still ⬜.)*
- ✅ **`DiskManager` ignored `retention_days` entirely** (`disk_manager.py`) — could delete today's footage. **Fixed:** honors `retention_days` (never deletes within the cutoff); `disk_monitor_task` passes the configured value.

### 🟠 High
- ✅ **EPERM/EROFS on delete swallowed; loops spin** (`storage_manager.py`, `disk_manager.py`) — read-only volume → `DiskManager` re-walked 926GB per batch (effectively infinite). **Fixed:** candidate list built once; cleanup aborts on `EROFS/EACCES/EPERM`; `disk_monitor_task` gates on `is_storage_writable()` and alerts instead.
- ✅ **`cleanup_deleted_files` wipes the DB on transient unmount** (`playback_db.py:661`) — every file "missing" → deletes all rows. **Fixed:** `db_maintenance.run_maintenance` skips orphan cleanup when storage isn't writable/mounted.
- ⬜ **O(N) DB scan per deleted file** (`storage_manager.py:176`) — quadratic cleanup. **Fix:** indexed `get_segment_by_path`.
- ⬜ **Full-volume `rglob` every cycle + on-demand stats endpoint** (`storage_manager.py:113,279`). **Fix:** drive from DB.
- ⬜ **`db_maintenance` resurrects/ fabricates segments** by estimating duration from file size (`db_maintenance.py:46`, `playback_db.py:716`).
- ⬜ **`write_failed` only on new-segment open** — see recording pipeline (fixed via growth check).

### 🟡 Medium
- ⬜ `delete_motion_events_in_range` inclusive `BETWEEN` deletes neighbor's boundary event (`storage_manager.py:212`).
- ⬜ Reserved-space math mixes `total` vs `used+free` denominators (`storage_manager.py:131`).
- ⬜ `_cleanup_empty_dirs` may rmdir live camera/cache dirs (`disk_manager.py:138`).
- ⬜ `db_maintenance` VACUUM holds exclusive lock vs live writers (`playback_db.py:752`).
- ⬜ Config singleton: no thread-safety, non-atomic `save()` can corrupt YAML; malformed YAML crashes startup (`config.py:30,49`). **Fix:** RLock + tmp-file `os.replace`; try/except around `safe_load`.
- ⬜ Runtime storage-threshold edits don't take effect (captured at startup) (`api.py:145`).
- ⬜ SD-card `fromisoformat` of untrusted ONVIF data unguarded; string min/max (`sd_card_manager.py:121,258`).

### ⚪ Low
- ⬜ Cache cleaner stats twice per file; only `*.mp4` (`cache_cleaner.py:78`).
- ⬜ Two divergent cache-cleaning implementations.
- ⬜ Alert id collision in same microsecond (`alert_system.py:48`).
- ⬜ `get()` dot-notation masks non-dict intermediates (`config.py:57`).

---

## Frontend — Playback (`playback.html`, `timeline-selector.js`)

### 🔴 Critical
- ✅ **`safeId` vs raw-id mismatch** — DOM elements created with sanitized `safeId` but lookups (zoom, timestamp, pan/drag) used unsanitized `cameraName`. Latent for this deployment (clean `cam_xxx` ids → `safeId` is a no-op) but would break zoom/overlays for any id with a space/`.`/`:`. **Fixed:** added a single `safeId()` helper and wrapped all 11 `getElementById` DOM-id lookups (behaviorally identical for clean ids, future-proof). Verified live: playback page loads with 0 console errors.
- ✅ **Triple `keydown` listeners** + duplicate `skipTime`/`changeSpeed` — Space double-toggled (appeared frozen), arrows seeked 10s not 5s, `,`/`.` frame-step force-resumed play (the shadowing duplicate `skipTime` routed through `seekToTime`). **Fixed:** removed the 2nd and 3rd listeners and the duplicate `skipTime`/`jumpToPercentage`/`changePlaybackSpeed`/`showKeyboardShortcuts`; folded the unique-and-useful bindings (↑/↓ speed, M mute) into the single surviving listener.

### 🟠 High
- ✅ `skipTime`/frame-step force-resume playback — resolved by removing the duplicate `skipTime` that routed through `seekToTime`; the surviving `skipTime` nudges `currentTime` directly without forcing play.
- ✅ Stale `loadRecordings` responses clobbered newer state → timeline/video desync (`playback.html`). **Fixed:** per-call sequence token (`loadRecordings._seq`) makes a superseded response bail before applying state. Verified with a rapid double-load.
- ⬜ `onloadedmetadata`/`onerror` reassigned repeatedly; `onerror` `replaceChildren` destroys the `<video>` still referenced (`playback.html:2568,2016`).
- ⬜ Always-on 100ms interval does DOM writes + regex-parses `src` forever, even when paused/backgrounded (`playback.html:3642`).
- ✅ **Export reports success on failure** (`playback.html:3335`) — looped `a.click()` (browsers drop all but first), no response check, always-green toast. **Fixed:** `performExport` now fetches each camera, checks `response.ok`, downloads via blob URL (revoked after), and reports per-camera success/failure counts.

### 🟡 Medium
- ⬜ Dead motion-visualization code — toggle exists, container never rendered (`playback.html:2203`).
- ⬜ In-video MOTION/PERSON/VEHICLE indicator never lights — keyed by id but `motionEvents` keyed by name (`playback.html:2374`).
- ⬜ `selectedCameras` holds ids but loops name them "cameraName" (`playback.html:2718`).
- ⬜ Timeline rebuilt wholesale on every AI toggle / tick (`playback.html:2044`). **Fix:** CSS class toggle + `DocumentFragment`.
- ⬜ `enforceFutureLimits` uses browser TZ not America/Chicago (`playback.html:1613`).
- ⬜ timeline-selector: success toast on every change (`:368`); per-instance resize listener never removed (`:152`); `toISOString` date → UTC day skew (`:378`).

### ⚪ Low
- ⬜ `changeSpeed` matches buttons by `textContent.includes` (`playback.html:3117`).
- ⬜ `formatTime` relies on OS locale (`:2326`).
- ⬜ Misleading quick-range names (`:1577`).
- ⬜ `togglePlayPause` flip-flops with N videos (`:2476`).
- ⬜ Wheel `preventDefault` blocks page scroll over players (`:3457`).

---

## Frontend — Live view & Settings (`index.html`, `settings.html`, `ui-utils.js`, `webrtc-client.js`, `fullscreen.html`)

### 🔴 Critical
- ✅ **Recording badge ignored `actively_writing`/`write_failed`** — initial render (`createCameraCard`, `index.html:2183`) showed green "REC" on first paint for a failed camera. **Fixed:** initial render now uses the same REC / NO DISK / STOPPED logic as the poll path. *(Remaining ⬜: a connected-but-stalled writer still shows REC until the growth check trips; consider an explicit "ARMED" state for motion-only idle.)*
- ✅ **Credentials shipped to browser** (`index.html:1881` consumed `rtsp_url` every 5s; `settings.html` round-tripped plaintext passwords). **Fixed:** `/api/cameras` no longer returns `rtsp_url`; `/api/config` masks passwords + RTSP creds (`SECRET_MASK`); `update_config` restores secrets from stored config on save (write-only), so editing other settings never wipes passwords. Verified: save round-trip preserves all 7 camera passwords.
- ✅ **Settings save clobbered cleanup config with defaults** (`settings.html`) → could zero `reserved_space_gb`. **Fixed:** `saveSettings` preserves existing `config.storage` and only overrides keys whose inputs are actually present.
- ✅ **Stored XSS on Settings** — **Fixed:** added an `escapeHtml` helper and applied it to all interpolated camera/device/DB strings (camera list, deletion history, recording/motion lists, discovered cameras); `editCamera`/`deleteCamera`/`selectDiscoveredCamera` now take an index instead of an interpolated string arg (no JS-string-in-attribute injection). Verified `escapeHtml` neutralizes `<img onerror>`.

### 🟠 High
- ⬜ MJPEG `<img>` connection leak on rebuild (`index.html:1938,1626`) — `innerHTML=''` without aborting sockets exhausts Chrome's 6-conn limit. **Fix:** `img.src='about:blank'` before clearing.
- ⬜ `setQuality` relies on global `event` (`index.html:1813`); also de-selects stream-mode buttons sharing `.quality-btn`.
- ⬜ `/ws/events` motion socket has no reconnect (`index.html:2982`) — dies on first server restart; unguarded `JSON.parse`; selector injection via `e.camera`.
- ⬜ No input validation on settings save (`settings.html:1770`) — NaN/out-of-range → corrupt config, possible boot failure.
- ⬜ `runManualCleanup` calls non-existent `loadStorageStatus()` (`settings.html:1531`) — cleanup errors after appearing to succeed. **Fix:** `updateStorageStatus()`.
- ⬜ "Save Changes" hard-redirects to `/` with no success/restart feedback (`settings.html:1822`).

### 🟡 Medium
- ⬜ `reconnectCamera` uses different `safeId` regex → status feedback targets nothing (`index.html:2928`).
- ⬜ Pollers never pause on hidden tab / open modal (`index.html:2978`).
- ⬜ Per-`<img>` handler closures never cleared (`index.html:2118`).
- ⬜ WebRTC reconnect can spawn parallel connections (`webrtc-client.js:141`).
- ⬜ Camera reorder has no own save path; indices stale (`settings.html:1218`).
- ⬜ `selectDiscoveredCamera` hand-rolled JSON-in-attribute escaping (`settings.html:1872`).
- ⬜ No empty/error/loading states for stats/async sections (`settings.html:1252`).
- ⬜ `ui-utils.js` 2s `initTooltips` DOM sweep forever (`:580`); modal Escape listener leaks (`:379`).
- ⬜ `fullscreen.html` hardcoded "RECORDING" status, MJPEG-only, 10s reload recovery (`:167`).

### ⚪ Low
- ⬜ `escapeHtml` wrong escaper for JS-string-in-attribute context (`index.html:2166`).
- ⬜ `navigateAway` breaks middle/ctrl-click (`index.html:2581`).
- ⬜ Timezone select hardcoded/dead (`settings.html:544`); `system-name` hardcoded/dead (`:1102`).
- ⬜ `fullscreen.html` contextmenu hijacked to navigate home (`:227`).

### Cross-cutting frontend
- ⬜ `escapeHtml` defined only in `index.html` but needed in `settings.html`.
- ⬜ `safeId` regex duplicated 4+ ways (one variant causes the reconnect bug). **Fix:** centralize.
- ⬜ No `document.hidden` gating on any poller.

---

## Changelog (2026-06-02)

Fixes applied this session (Tier 3 detection + quick-win runtime bugs):

| File | Change |
|------|--------|
| `nvr/web/settings_api.py` | `config.save_config()` → `config.save()` (×2) — settings saves no longer 500 |
| `nvr/web/api.py` | `get_camera_health`: bind `recorder.camera_name`, add `write_failed` status + fields |
| `nvr/web/api.py` | `get_all_cameras_health`: add `write_failed` status + `actively_writing`/`write_failed` fields |
| `nvr/web/api.py` | `live_stream`: bind `camera_name = recorder.camera_name` |
| `nvr/web/api.py` | health-monitor loop: call `alert_system.check_storage_writable(config.is_storage_writable())` |
| `nvr/core/config.py` | `storage_path` creates dir once (no mountpoint recreation on unmount); added `is_storage_writable()` |
| `nvr/core/recorder.py` | added `_check_segment_growth()` mid-segment write-loss detection; reworked `write_failed`/`actively_writing` ownership |
| `nvr/core/alert_system.py` | added `CAMERA_WRITE_FAILED` + `STORAGE_UNWRITABLE` alert types; `check_camera_health` fires on `write_failed`; added `check_storage_writable()` |
| `nvr/templates/index.html` | initial card render uses REC / NO DISK / STOPPED logic |
| `nvr/templates/playback.html` | removed dev "Test 3hr" button + `loadTestRange()` |

### Changelog (2026-06-02, part 2 — #2 credentials, #6 export, #10 cleanup)

| File | Change |
|------|--------|
| `nvr/web/playback_api.py` | `export_clip`: correct kwargs + injected `Request`/`BackgroundTasks`; `except HTTPException: raise` |
| `nvr/templates/playback.html` | `performExport`: sequential blob downloads, `response.ok` checks, honest per-camera success/fail toast |
| `nvr/web/api.py` | `/api/cameras` drops `rtsp_url`; `disk_monitor_task` gates on writability + passes `retention_days`/`protected_paths`; cleanup callers pass active segments |
| `nvr/web/settings_api.py` | `SECRET_MASK`; `_redact_cameras` (GET) + `_restore_camera_secrets`/`_reapply_rtsp_credentials` (POST write-only password handling) |
| `nvr/core/recorder.py` | `RecorderManager.get_active_segment_paths()`; flag-consistency fix (`actively_writing = not write_failed`) |
| `nvr/core/disk_manager.py` | `cleanup_old_recordings` honors `retention_days` + `protected_paths`; candidate list built once; abort on EROFS/EACCES/EPERM; `_cleanup_empty_dirs` skips cache/active dirs |
| `nvr/core/storage_manager.py` | `check_and_cleanup`/`_cleanup_old_files` accept `protected_paths`; abort on EROFS/EACCES/EPERM |
| `nvr/core/db_maintenance.py` | skip orphan-entry cleanup when storage not writable/mounted |

### Changelog (2026-06-02, part 5 — live fullscreen box-zoom)

Pre-existing bug (not from this session's changes): the live view streams via
WebSocket→`<canvas>` (`streamingMode === 'websocket'`), but the fullscreen
zoom functions only transformed the `<img>` (`#fullscreen-stream`), which is
hidden in that mode — so drawing a zoom box (and +/−/wheel/reset) changed
`zoomState` but nothing moved on screen. `zoomToSelection` also read the hidden
img's `naturalWidth/Height` (0) → `NaN` translate → transform dropped.

| File | Change |
|------|--------|
| `nvr/templates/index.html` | `updateZoom` transforms **both** the img and the canvas (whichever is visible); `zoomToSelection` reads intrinsic size from the active element with a wrapper-size fallback (no more NaN); double-click-to-reset rebinds to the wrapper (the img never received it in canvas mode) |

Verified in a real browser (WebSocket mode): drawing a box zooms the visible
canvas to `scale(2.25)` with finite translate, reset returns to 100%, 0 console
errors. Playback box-zoom uses a real `<video>` element and was verified
already working (unchanged).

### Tests
- `test_config.py::TestStorageWritability` / `TestStoragePathMountSafety` — `is_storage_writable` true/false/no-mkdir; `storage_path` creates once, doesn't recreate after unmount.
- `test_recorder.py::TestWriteFailureDetection` — `_check_segment_growth` baseline reset, growth→healthy, no-growth→write_failed, missing-file→write_failed, sampling gate.
- `test_recorder.py::TestActiveSegmentPaths` — `get_active_segment_paths` returns current segments, ignores recorders without one.
- `test_alert_system.py::TestWriteFailureAlerts` — `CAMERA_WRITE_FAILED` on `write_failed`; `STORAGE_UNWRITABLE` on probe false + recovery; no alert when writable; no re-fire while still failing.
- `test_disk_manager.py` (new) — retention honored, active segments protected, EPERM aborts (no infinite loop), empty-dir cleanup skips cache/active dirs.
- `test_settings_api.py` (new) — password/RTSP masking, no input mutation, write-only restore (masked/blank→restored, new→kept), full GET→POST round-trip preserves secret.

Full unit suite: **330 passed** (3 consecutive runs); the occasional `test_frame_rate_limiting` blip is a pre-existing wall-clock flake unrelated to these changes.

### Changelog (2026-06-02, part 3 — #1 authentication)

Opt-in HTTP Basic auth (chosen for an isolated camera-only LAN — simple, no frontend changes).

| File | Change |
|------|--------|
| `nvr/web/api.py` | `_check_basic_auth()` (constant-time) + `basic_auth_middleware` (HTTP-only, so WebSockets stay open); active when `web.auth_password` is set; OPTIONS preflight exempt |
| `config/config.yaml.bar-example` | documented `web.auth_username` / `web.auth_password` (empty = disabled) |
| `tests/unit/test_api.py` | `TestBasicAuthCheck` — correct/wrong/missing/malformed creds, colon-in-password, non-Basic scheme |

To enable: set `web.auth_password` (and optionally `web.auth_username`, default `admin`) in `config/config.yaml`, then `./restart.sh`. Verified live: 401 + `WWW-Authenticate` without creds, 200 with. Full suite: **338 passed**.

### Changelog (2026-06-02, part 4 — write-failure detector is now signal-aware)

A weak-signal camera (delivers frames slowly / stalls) could make a segment
file stop growing and be mislabeled as a disk failure ("NO DISK" +
`CAMERA_WRITE_FAILED`). Refined so the detector distinguishes the two:

| File | Change |
|------|--------|
| `nvr/core/recorder.py` | `_check_segment_growth` only flags `write_failed` when no growth AND ≥15 frames were written in the window. Too few frames → treated as a stream stall (surfaces as `stale`/`degraded` via `last_frame_time`), not a disk failure. Added `_frames_written_total`/`_frames_at_last_check`. |
| `tests/unit/test_recorder.py` | split into no-growth-**with**-frames (→ write_failed) and no-growth-**few**-frames (→ stall, not flagged). |

Real disk failure (healthy camera, dead disk) still flags — frames keep arriving at full rate. Full suite: **339 passed**.
