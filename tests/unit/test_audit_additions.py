"""Unit tests for audit-pass additions: alert persistence, motion search,
and orphaned-file cleanup."""

import os
import time
from datetime import datetime, timedelta

from nvr.core.alert_system import Alert, AlertType, AlertLevel


class TestAlertPersistence:
    def test_add_get_acknowledge(self, playback_db):
        a = Alert(
            AlertType.CAMERA_WRITE_FAILED,
            AlertLevel.CRITICAL,
            "Camera X not writing",
            camera_name="X",
            details={"k": 1},
        )
        alert_id = playback_db.add_alert(a.to_dict())
        assert alert_id > 0

        unack = playback_db.get_alerts(unacknowledged_only=True)
        assert len(unack) == 1
        assert unack[0]["message"] == "Camera X not writing"
        assert unack[0]["details"] == {"k": 1}  # JSON round-trips
        assert unack[0]["acknowledged"] is False

        assert playback_db.acknowledge_alert(alert_id) is True
        assert playback_db.get_alerts(unacknowledged_only=True) == []

    def test_acknowledge_missing_returns_false(self, playback_db):
        assert playback_db.acknowledge_alert(999999) is False

    def test_acknowledge_all(self, playback_db):
        for i in range(3):
            playback_db.add_alert(Alert(AlertType.STORAGE_LOW, AlertLevel.WARNING, f"low {i}").to_dict())
        assert playback_db.acknowledge_all_alerts() == 3
        assert playback_db.get_alerts(unacknowledged_only=True) == []

    def test_cleanup_old_alerts_only_acknowledged(self, playback_db):
        old = (datetime.now() - timedelta(days=40)).isoformat()
        # old + acknowledged -> pruned; old + unacknowledged -> kept
        aid = playback_db.add_alert(
            {"type": "storage_low", "level": "warning", "message": "old ack", "timestamp": old, "details": {}}
        )
        playback_db.acknowledge_alert(aid)
        playback_db.add_alert(
            {"type": "storage_low", "level": "warning", "message": "old open", "timestamp": old, "details": {}}
        )
        pruned = playback_db.cleanup_old_alerts(days=30)
        assert pruned == 1
        assert len(playback_db.get_alerts(unacknowledged_only=True)) == 1


class TestMotionSearch:
    def _seed(self, db):
        base = datetime(2026, 6, 1, 12, 0, 0)
        db.add_motion_event("cam_a", base, intensity=10.0, event_type="motion", camera_name="Alley")
        db.add_motion_event(
            "cam_a", base + timedelta(minutes=1), intensity=80.0, event_type="motion", camera_name="Alley"
        )
        db.add_motion_event("cam_b", base + timedelta(minutes=2), intensity=50.0, event_type="ai", camera_name="Patio")
        return base

    def test_search_all(self, playback_db):
        self._seed(playback_db)
        res = playback_db.search_motion_events()
        assert res["total"] == 3
        # newest first
        assert res["events"][0]["camera_name"] == "Patio"

    def test_filter_by_camera_and_intensity(self, playback_db):
        self._seed(playback_db)
        res = playback_db.search_motion_events(camera="cam_a", min_intensity=50.0)
        assert res["total"] == 1
        assert res["events"][0]["intensity"] == 80.0

    def test_filter_by_event_type(self, playback_db):
        self._seed(playback_db)
        res = playback_db.search_motion_events(event_type="ai")
        assert res["total"] == 1
        assert res["events"][0]["camera_name"] == "Patio"

    def test_paging(self, playback_db):
        self._seed(playback_db)
        page1 = playback_db.search_motion_events(limit=2, offset=0)
        page2 = playback_db.search_motion_events(limit=2, offset=2)
        assert len(page1["events"]) == 2
        assert len(page2["events"]) == 1
        assert page1["total"] == 3 and page2["total"] == 3

    def test_camera_match_by_name(self, playback_db):
        self._seed(playback_db)
        res = playback_db.search_motion_events(camera="Patio")
        assert res["total"] == 1


class TestOrphanCleanup:
    def test_finds_aged_orphan_spares_new_and_tracked(self, playback_db, temp_dir):
        storage = temp_dir / "store"
        cam = storage / "cam_a"
        cam.mkdir(parents=True)
        old = time.time() - 7200  # 2h

        # 1) genuine orphan (old, untracked)
        orphan = cam / "20260601_000000.mp4"
        orphan.write_bytes(b"x" * 2048)
        os.utime(orphan, (old, old))

        # 2) too-new orphan -> spared by min-age
        fresh = cam / "20260601_001000.mp4"
        fresh.write_bytes(b"x" * 2048)

        # 3) tracked file -> spared
        tracked = cam / "20260601_002000.mp4"
        tracked.write_bytes(b"x" * 2048)
        os.utime(tracked, (old, old))
        playback_db.add_segment(camera_id="cam_a", file_path=str(tracked), start_time=datetime(2026, 6, 1, 0, 20))

        # 4) _h264 variant of the tracked file -> spared
        h264 = cam / "20260601_002000_h264.mp4"
        h264.write_bytes(b"x" * 2048)
        os.utime(h264, (old, old))

        orphans = {str(p) for p, _ in playback_db.find_orphaned_files(storage, min_age_seconds=3600)}
        assert str(orphan) in orphans
        assert str(fresh) not in orphans
        assert str(tracked) not in orphans
        assert str(h264) not in orphans

    def test_dry_run_deletes_nothing(self, playback_db, temp_dir):
        storage = temp_dir / "store2"
        cam = storage / "cam_a"
        cam.mkdir(parents=True)
        old = time.time() - 7200
        orphan = cam / "20260601_000000.mp4"
        orphan.write_bytes(b"x" * 2048)
        os.utime(orphan, (old, old))

        report = playback_db.cleanup_orphaned_files(storage, dry_run=True, min_age_seconds=3600)
        assert report["orphan_count"] == 1
        assert report["deleted_count"] == 0
        assert orphan.exists()  # nothing deleted

        report = playback_db.cleanup_orphaned_files(storage, dry_run=False, min_age_seconds=3600)
        assert report["deleted_count"] == 1
        assert not orphan.exists()

    def test_skips_hidden_cache_dirs(self, playback_db, temp_dir):
        storage = temp_dir / "store3"
        cache = storage / ".speed_cache"
        cache.mkdir(parents=True)
        old = time.time() - 7200
        cached = cache / "anything.mp4"
        cached.write_bytes(b"x" * 2048)
        os.utime(cached, (old, old))

        orphans = playback_db.find_orphaned_files(storage, min_age_seconds=3600)
        assert orphans == []
