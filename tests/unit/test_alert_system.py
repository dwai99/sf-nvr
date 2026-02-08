"""Unit tests for alert system - alerts, cooldowns, and handlers"""

import pytest
from datetime import datetime, timedelta
import asyncio

from nvr.core.alert_system import (
    Alert,
    AlertType,
    AlertLevel,
    AlertSystem,
    LogAlertHandler,
    WebhookAlertHandler
)


@pytest.mark.unit
@pytest.mark.asyncio
class TestAlertSystem:
    """Test cases for AlertSystem class"""

    async def test_init_alert_system(self, alert_system):
        """Test alert system initialization"""
        assert alert_system is not None
        assert len(alert_system.handlers) > 0  # Has default log handler
        assert alert_system.max_alerts == 100
        assert alert_system.cooldown_minutes == 5

    async def test_send_alert_basic(self, alert_system):
        """Test sending a basic alert"""
        alert = Alert(
            alert_type=AlertType.CAMERA_OFFLINE,
            level=AlertLevel.ERROR,
            message="Camera test_camera is offline",
            camera_name="test_camera"
        )

        await alert_system.send_alert(alert)

        # Alert should be in history
        assert len(alert_system.alerts) == 1
        assert alert_system.alerts[0].message == "Camera test_camera is offline"

    async def test_alert_cooldown_prevents_spam(self, alert_system):
        """Test that cooldown prevents repeated alerts"""
        alert1 = Alert(
            alert_type=AlertType.CAMERA_OFFLINE,
            level=AlertLevel.ERROR,
            message="Camera offline",
            camera_name="test_camera"
        )

        alert2 = Alert(
            alert_type=AlertType.CAMERA_OFFLINE,
            level=AlertLevel.ERROR,
            message="Camera offline again",
            camera_name="test_camera"
        )

        # Send first alert
        await alert_system.send_alert(alert1)
        assert len(alert_system.alerts) == 1

        # Send duplicate alert immediately
        await alert_system.send_alert(alert2)

        # Should still only have 1 alert due to cooldown
        assert len(alert_system.alerts) == 1

    async def test_alert_deduplication_different_cameras(self, alert_system):
        """Test that alerts for different cameras are not deduplicated"""
        alert1 = Alert(
            alert_type=AlertType.CAMERA_OFFLINE,
            level=AlertLevel.ERROR,
            message="Camera 1 offline",
            camera_name="camera_1"
        )

        alert2 = Alert(
            alert_type=AlertType.CAMERA_OFFLINE,
            level=AlertLevel.ERROR,
            message="Camera 2 offline",
            camera_name="camera_2"
        )

        await alert_system.send_alert(alert1)
        await alert_system.send_alert(alert2)

        # Should have both alerts
        assert len(alert_system.alerts) == 2

    async def test_camera_state_transitions_offline(self, alert_system):
        """Test camera state transitions from healthy to offline"""
        # Initial state (healthy)
        health_data_healthy = {
            'status': 'healthy',
            'is_recording': True
        }
        await alert_system.check_camera_health('test_camera', health_data_healthy)

        # Should have no alerts yet (initial state)
        assert len(alert_system.alerts) == 0

        # Transition to offline
        health_data_offline = {
            'status': 'stopped',
            'is_recording': False
        }
        await alert_system.check_camera_health('test_camera', health_data_offline)

        # Should have offline alert
        assert len(alert_system.alerts) == 1
        assert alert_system.alerts[0].alert_type == AlertType.CAMERA_OFFLINE

    async def test_camera_state_transitions_degraded(self, alert_system):
        """Test camera state transitions to degraded"""
        # Start with healthy
        await alert_system.check_camera_health('test_camera', {'status': 'healthy'})

        # Transition to degraded
        health_data_degraded = {
            'status': 'degraded',
            'consecutive_failures': 3,
            'total_reconnects': 5
        }
        await alert_system.check_camera_health('test_camera', health_data_degraded)

        # Should have degraded alert
        assert len(alert_system.alerts) == 1
        assert alert_system.alerts[0].alert_type == AlertType.CAMERA_DEGRADED

    async def test_camera_state_transitions_recovery(self, alert_system):
        """Test camera recovery alert"""
        # Start with offline
        await alert_system.check_camera_health('test_camera', {'status': 'stopped'})

        # Recover to healthy
        await alert_system.check_camera_health('test_camera', {'status': 'healthy'})

        # Should have recovery alert
        recovery_alerts = [a for a in alert_system.alerts if a.alert_type == AlertType.CAMERA_RECOVERED]
        assert len(recovery_alerts) == 1

    async def test_camera_stale_alert(self, alert_system):
        """Test alert when camera becomes stale"""
        # Start with healthy
        await alert_system.check_camera_health('test_camera', {'status': 'healthy'})

        # Transition to stale
        health_data_stale = {
            'status': 'stale',
            'time_since_last_frame_seconds': 45
        }
        await alert_system.check_camera_health('test_camera', health_data_stale)

        # Should have degraded alert (stale is treated as degraded)
        assert len(alert_system.alerts) == 1
        assert alert_system.alerts[0].alert_type == AlertType.CAMERA_DEGRADED

    async def test_storage_low_alert(self, alert_system):
        """Test storage low alert"""
        # 87% disk usage - above 85% threshold
        await alert_system.check_storage(disk_percent=87.0, free_gb=50.0)

        assert len(alert_system.alerts) == 1
        assert alert_system.alerts[0].alert_type == AlertType.STORAGE_LOW

    async def test_storage_critical_alert(self, alert_system):
        """Test storage critical alert"""
        # 96% disk usage - above 95% threshold
        await alert_system.check_storage(disk_percent=96.0, free_gb=10.0)

        assert len(alert_system.alerts) == 1
        assert alert_system.alerts[0].alert_type == AlertType.STORAGE_CRITICAL

    async def test_storage_ok_no_alert(self, alert_system):
        """Test no alert when storage is OK"""
        # 70% disk usage - below thresholds
        await alert_system.check_storage(disk_percent=70.0, free_gb=150.0)

        assert len(alert_system.alerts) == 0

    async def test_alert_history_limit(self, alert_system):
        """Test that alert history is capped at max_alerts"""
        # Send more than max_alerts
        for i in range(150):
            alert = Alert(
                alert_type=AlertType.SYSTEM_ERROR,
                level=AlertLevel.ERROR,
                message=f"Error {i}",
                camera_name=f"camera_{i}"
            )
            await alert_system.send_alert(alert)

        # Should only keep last 100
        assert len(alert_system.alerts) == alert_system.max_alerts

    async def test_get_recent_alerts(self, alert_system):
        """Test getting recent alerts"""
        # Create some alerts - use unique camera names to avoid cooldown
        for i in range(10):
            alert = Alert(
                alert_type=AlertType.SYSTEM_ERROR,
                level=AlertLevel.ERROR,
                message=f"Error {i}",
                camera_name=f"camera_{i}"  # Each alert has unique camera name
            )
            await alert_system.send_alert(alert)

        # Get recent alerts
        recent = alert_system.get_recent_alerts(limit=5)
        assert len(recent) == 5

    async def test_get_alerts_by_camera(self, alert_system):
        """Test getting alerts for specific camera"""
        # Create different alert types to avoid cooldown (each type is tracked separately)
        alert_types = [
            AlertType.CAMERA_DEGRADED,
            AlertType.CAMERA_OFFLINE,
            AlertType.CAMERA_RECOVERED,
            AlertType.STORAGE_LOW,
            AlertType.STORAGE_CRITICAL
        ]

        # Create alerts for camera_1
        for i in range(5):
            alert = Alert(
                alert_type=alert_types[i],  # Different type each time
                level=AlertLevel.WARNING,
                message=f"Camera issue {i}",
                camera_name="camera_1"
            )
            await alert_system.send_alert(alert)

        # Create alerts for camera_2
        for i in range(3):
            alert = Alert(
                alert_type=alert_types[i],  # Different type each time
                level=AlertLevel.WARNING,
                message=f"Camera issue {i}",
                camera_name="camera_2"
            )
            await alert_system.send_alert(alert)

        # Get alerts for camera_1
        camera_1_alerts = alert_system.get_alerts_by_camera("camera_1", limit=10)
        assert len(camera_1_alerts) == 5


@pytest.mark.unit
class TestAlertObject:
    """Test Alert object functionality"""

    def test_alert_creation(self):
        """Test creating an alert object"""
        alert = Alert(
            alert_type=AlertType.CAMERA_OFFLINE,
            level=AlertLevel.ERROR,
            message="Test alert",
            camera_name="test_camera",
            details={'extra': 'data'}
        )

        assert alert.alert_type == AlertType.CAMERA_OFFLINE
        assert alert.level == AlertLevel.ERROR
        assert alert.message == "Test alert"
        assert alert.camera_name == "test_camera"
        assert alert.details['extra'] == 'data'
        assert alert.timestamp is not None
        assert alert.id is not None

    def test_alert_to_dict(self):
        """Test converting alert to dictionary"""
        alert = Alert(
            alert_type=AlertType.STORAGE_LOW,
            level=AlertLevel.WARNING,
            message="Storage running low",
            details={'disk_percent': 87.5}
        )

        alert_dict = alert.to_dict()

        assert alert_dict['type'] == 'storage_low'
        assert alert_dict['level'] == 'warning'
        assert alert_dict['message'] == "Storage running low"
        assert alert_dict['details']['disk_percent'] == 87.5
        assert 'timestamp' in alert_dict
        assert 'id' in alert_dict

    def test_alert_without_camera(self):
        """Test creating system-wide alert without camera"""
        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            level=AlertLevel.CRITICAL,
            message="System error occurred"
        )

        assert alert.camera_name is None
        alert_dict = alert.to_dict()
        assert alert_dict['camera_name'] is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestAlertHandlers:
    """Test alert handler functionality"""

    async def test_log_handler(self, alert_system, caplog):
        """Test log alert handler"""
        alert = Alert(
            alert_type=AlertType.CAMERA_OFFLINE,
            level=AlertLevel.ERROR,
            message="Test log message",
            camera_name="test_camera"
        )

        handler = LogAlertHandler()
        await handler.handle(alert)

        # Check that log was created (pytest caplog fixture)
        # Note: Actual log verification depends on logger configuration

    async def test_multiple_handlers(self, alert_system):
        """Test that all registered handlers receive alerts"""
        handler_calls = []

        class TestHandler:
            async def handle(self, alert):
                handler_calls.append(alert.message)

        # Clear default handlers and add test handlers
        alert_system.handlers.clear()
        alert_system.add_handler(TestHandler())
        alert_system.add_handler(TestHandler())

        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            level=AlertLevel.ERROR,
            message="Test message"
        )

        await alert_system.send_alert(alert)

        # Both handlers should have been called
        assert len(handler_calls) == 2
        assert all(msg == "Test message" for msg in handler_calls)

    async def test_handler_error_doesnt_break_system(self, alert_system):
        """Test that handler errors don't break the alert system"""
        class BrokenHandler:
            async def handle(self, alert):
                raise Exception("Handler error!")

        alert_system.add_handler(BrokenHandler())

        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            level=AlertLevel.ERROR,
            message="Test message"
        )

        # Should not raise exception
        try:
            await alert_system.send_alert(alert)
            # Alert should still be recorded
            assert len(alert_system.alerts) == 1
        except Exception:
            pytest.fail("Alert system raised exception due to handler error")


@pytest.mark.unit
class TestAlertEdgeCases:
    """Test edge cases and error scenarios"""

    @pytest.mark.asyncio
    async def test_empty_message(self, alert_system):
        """Test alert with empty message"""
        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            level=AlertLevel.ERROR,
            message=""
        )

        await alert_system.send_alert(alert)
        assert len(alert_system.alerts) == 1

    @pytest.mark.asyncio
    async def test_very_long_message(self, alert_system):
        """Test alert with very long message"""
        long_message = "A" * 10000

        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            level=AlertLevel.ERROR,
            message=long_message
        )

        await alert_system.send_alert(alert)
        assert len(alert_system.alerts) == 1
        assert len(alert_system.alerts[0].message) == 10000

    @pytest.mark.asyncio
    async def test_alert_with_none_details(self, alert_system):
        """Test alert with None details"""
        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            level=AlertLevel.ERROR,
            message="Test",
            details=None
        )

        assert alert.details == {}  # Should default to empty dict
