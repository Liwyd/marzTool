import logging
import time
from datetime import datetime, timezone


class VolumeLimiter:
    BYTES_PER_GB = 1024 * 1024 * 1024

    def __init__(self, client, config, db, logger: logging.Logger = None):
        self.client = client
        self.config = config
        self.db = db
        self.log = logger or logging.getLogger("volume_limiter")

    def process_cycle(self, users: list = None) -> list[dict]:
        limit_gb = self.config.get_volume_limit_gb()
        limit_bytes = limit_gb * self.BYTES_PER_GB
        disabled_users = []

        if users is None:
            try:
                users = self.client.get_all_users()
            except Exception as e:
                self.log.error("Failed to fetch users: %s", e)
                return []

        for user in users:
            username = user.get("username", "")
            status = user.get("status", "")

            if not username:
                continue

            if status != "active":
                continue

            if self.db.is_exempt(username):
                continue

            used = max(
                user.get("used_traffic", 0),
                user.get("lifetime_used_traffic", 0),
            )

            if used < limit_bytes:
                continue

            if self.db.was_already_notified_volume(username):
                continue

            admin_username = None
            admin_obj = user.get("admin")
            if admin_obj and isinstance(admin_obj, dict):
                admin_username = admin_obj.get("username")

            try:
                self.client.put_user(username, {"status": "disabled"})
                self.log.info(
                    "Disabled user %s — used %d GB (limit %d GB)",
                    username, used / self.BYTES_PER_GB, limit_gb,
                )
            except Exception as e:
                self.log.error("Failed to disable user %s: %s", username, e)
                continue

            now = datetime.now(timezone.utc).isoformat()
            notif_id = self.db.add_volume_notification(
                username=username,
                admin_username=admin_username,
                used_traffic_bytes=used,
                disabled_at=now,
            )

            used_gb = used / self.BYTES_PER_GB
            disabled_users.append({
                "notif_id": notif_id,
                "username": username,
                "admin_username": admin_username,
                "used_gb": round(used_gb, 2),
                "limit_gb": limit_gb,
            })

        return disabled_users
