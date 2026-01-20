"""Alert system for camera failures and system events"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Callable, Optional
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of alerts"""
    CAMERA_OFFLINE = "camera_offline"
    CAMERA_DEGRADED = "camera_degraded"
    CAMERA_RECOVERED = "camera_recovered"
    STORAGE_LOW = "storage_low"
    STORAGE_CRITICAL = "storage_critical"
    DATABASE_ERROR = "database_error"
    SYSTEM_ERROR = "system_error"


class Alert:
    """Represents a system alert"""

    def __init__(
        self,
        alert_type: AlertType,
        level: AlertLevel,
        message: str,
        camera_name: Optional[str] = None,
        details: Optional[Dict] = None
    ):
        self.alert_type = alert_type
        self.level = level
        self.message = message
        self.camera_name = camera_name
        self.details = details or {}
        self.timestamp = datetime.now()
        self.id = f"{alert_type.value}_{self.timestamp.timestamp()}"

    def to_dict(self) -> Dict:
        """Convert alert to dictionary"""
        return {
            'id': self.id,
            'type': self.alert_type.value,
            'level': self.level.value,
            'message': self.message,
            'camera_name': self.camera_name,
            'details': self.details,
            'timestamp': self.timestamp.isoformat()
        }


class AlertHandler:
    """Base class for alert handlers"""

    async def handle(self, alert: Alert):
        """Handle an alert"""
        raise NotImplementedError


class LogAlertHandler(AlertHandler):
    """Log alerts to the application log"""

    async def handle(self, alert: Alert):
        log_message = f"[{alert.level.value.upper()}] {alert.message}"
        if alert.camera_name:
            log_message = f"[{alert.camera_name}] {log_message}"

        if alert.level == AlertLevel.CRITICAL or alert.level == AlertLevel.ERROR:
            logger.error(log_message)
        elif alert.level == AlertLevel.WARNING:
            logger.warning(log_message)
        else:
            logger.info(log_message)


class WebhookAlertHandler(AlertHandler):
    """Send alerts to a webhook endpoint"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def handle(self, alert: Alert):
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=alert.to_dict(),
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"Webhook returned status {response.status}")
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")


class AlertSystem:
    """Central alert management system"""

    def __init__(self):
        self.handlers: List[AlertHandler] = []
        self.alerts: List[Alert] = []
        self.max_alerts = 100  # Keep last 100 alerts in memory
        self.alert_cooldowns: Dict[str, datetime] = {}
        self.cooldown_minutes = 5  # Don't repeat same alert within 5 minutes

        # Add default log handler
        self.add_handler(LogAlertHandler())

        # Camera state tracking
        self.camera_states: Dict[str, str] = {}  # camera_name -> status

    def add_handler(self, handler: AlertHandler):
        """Add an alert handler"""
        self.handlers.append(handler)
        logger.info(f"Added alert handler: {handler.__class__.__name__}")

    async def send_alert(self, alert: Alert):
        """Send an alert to all handlers"""

        # Check cooldown to prevent alert spam
        cooldown_key = f"{alert.alert_type.value}_{alert.camera_name or 'system'}"
        if cooldown_key in self.alert_cooldowns:
            time_since_last = datetime.now() - self.alert_cooldowns[cooldown_key]
            if time_since_last < timedelta(minutes=self.cooldown_minutes):
                logger.debug(f"Alert {cooldown_key} in cooldown, skipping")
                return

        # Update cooldown
        self.alert_cooldowns[cooldown_key] = datetime.now()

        # Store alert
        self.alerts.append(alert)
        if len(self.alerts) > self.max_alerts:
            self.alerts.pop(0)

        # Send to all handlers
        for handler in self.handlers:
            try:
                await handler.handle(alert)
            except Exception as e:
                logger.error(f"Error in alert handler {handler.__class__.__name__}: {e}")

    def get_recent_alerts(self, limit: int = 50) -> List[Dict]:
        """Get recent alerts"""
        return [a.to_dict() for a in self.alerts[-limit:]]

    def get_alerts_by_camera(self, camera_name: str, limit: int = 20) -> List[Dict]:
        """Get recent alerts for a specific camera"""
        camera_alerts = [a for a in self.alerts if a.camera_name == camera_name]
        return [a.to_dict() for a in camera_alerts[-limit:]]

    async def check_camera_health(self, camera_name: str, health_data: Dict):
        """Check camera health and send alerts if needed"""
        status = health_data.get('status', 'unknown')
        previous_status = self.camera_states.get(camera_name)

        # Track state change
        self.camera_states[camera_name] = status

        # Don't alert on initial state
        if previous_status is None:
            return

        # Alert on status changes
        if status == 'stopped' and previous_status != 'stopped':
            await self.send_alert(Alert(
                alert_type=AlertType.CAMERA_OFFLINE,
                level=AlertLevel.ERROR,
                message=f"Camera {camera_name} is offline",
                camera_name=camera_name,
                details={'previous_status': previous_status}
            ))

        elif status == 'degraded' and previous_status == 'healthy':
            await self.send_alert(Alert(
                alert_type=AlertType.CAMERA_DEGRADED,
                level=AlertLevel.WARNING,
                message=f"Camera {camera_name} is experiencing connection issues",
                camera_name=camera_name,
                details={
                    'consecutive_failures': health_data.get('consecutive_failures'),
                    'total_reconnects': health_data.get('total_reconnects')
                }
            ))

        elif status == 'stale' and previous_status in ['healthy', 'degraded']:
            await self.send_alert(Alert(
                alert_type=AlertType.CAMERA_DEGRADED,
                level=AlertLevel.WARNING,
                message=f"Camera {camera_name} has not received frames recently",
                camera_name=camera_name,
                details={
                    'time_since_last_frame': health_data.get('time_since_last_frame_seconds')
                }
            ))

        elif status == 'healthy' and previous_status in ['stopped', 'degraded', 'stale']:
            await self.send_alert(Alert(
                alert_type=AlertType.CAMERA_RECOVERED,
                level=AlertLevel.INFO,
                message=f"Camera {camera_name} has recovered",
                camera_name=camera_name,
                details={'previous_status': previous_status}
            ))

    async def check_storage(self, disk_percent: float, free_gb: float):
        """Check storage and send alerts if needed"""
        if disk_percent >= 95:
            await self.send_alert(Alert(
                alert_type=AlertType.STORAGE_CRITICAL,
                level=AlertLevel.CRITICAL,
                message=f"Storage critically low: {disk_percent:.1f}% used, {free_gb:.1f} GB free",
                details={'disk_percent': disk_percent, 'free_gb': free_gb}
            ))
        elif disk_percent >= 85:
            await self.send_alert(Alert(
                alert_type=AlertType.STORAGE_LOW,
                level=AlertLevel.WARNING,
                message=f"Storage running low: {disk_percent:.1f}% used, {free_gb:.1f} GB free",
                details={'disk_percent': disk_percent, 'free_gb': free_gb}
            ))


# Global alert system instance
alert_system = AlertSystem()
