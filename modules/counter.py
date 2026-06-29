import logging
from datetime import datetime, timezone


class Counter:
    TRAFFIC_THRESHOLD = 500 * 1024 * 1024
    EXPIRE_GAP_THRESHOLD = 7 * 24 * 60 * 60

    def __init__(self, client, db, logger: logging.Logger = None):
        self.client = client
        self.db = db
        self.log = logger or logging.getLogger("counter")

    def sync(self, users: list = None):
        if users is None:
            users = self.client.get_all_users()
        now = datetime.now(timezone.utc).isoformat()

        for user in users:
            username = user["username"]
            admin = user.get("admin")
            if not admin or not admin.get("username"):
                continue
            admin_username = admin["username"]

            used_traffic = user.get("used_traffic", 0) or 0
            lifetime_used = user.get("lifetime_used_traffic", 0) or 0
            expire = user.get("expire")
            created_at = user.get("created_at", "")
            total_traffic = max(used_traffic, lifetime_used)

            existing = self.db.get_counter_user(username)

            if not existing:
                if total_traffic >= self.TRAFFIC_THRESHOLD:
                    self.db.upsert_counter_user(
                        username, admin_username, now,
                        expire, created_at, total_traffic,
                    )
                    self.db.increment_counter_total(admin_username)
                    self.log.info("Counter: counted %s (admin=%s, traffic=%dMB)",
                                  username, admin_username, total_traffic // (1024 * 1024))
            else:
                prev_created = existing.get("last_created_at", "")
                if prev_created and created_at and created_at != prev_created:
                    self.db.upsert_counter_user(
                        username, admin_username, now,
                        expire, created_at, total_traffic,
                    )
                    self.db.increment_counter_total(admin_username)
                    self.log.info("Counter: re-counted %s (admin=%s, recreated)",
                                  username, admin_username)

                elif expire is not None and existing.get("last_expire") is not None:
                    gap = expire - existing["last_expire"]
                    if gap > self.EXPIRE_GAP_THRESHOLD:
                        self.db.upsert_counter_user(
                            username, admin_username, now,
                            expire, created_at, total_traffic,
                        )
                        self.db.increment_counter_total(admin_username)
                        gap_days = gap // (24 * 60 * 60)
                        self.log.info("Counter: re-counted %s (admin=%s, expire +%dd)",
                                      username, admin_username, gap_days)
                    else:
                        self.db.upsert_counter_user(
                            username, admin_username, existing["counted_at"],
                            expire, created_at, total_traffic,
                        )
                else:
                    self.db.upsert_counter_user(
                        username, admin_username, existing["counted_at"],
                        expire, created_at, total_traffic,
                    )

    def detect_resets(self, users: list = None):
        if users is None:
            users = self.client.get_all_users()
        now = datetime.now(timezone.utc).isoformat()

        for user in users:
            username = user["username"]
            admin = user.get("admin")
            if not admin or not admin.get("username"):
                continue
            admin_username = admin["username"]

            used_traffic = user.get("used_traffic", 0) or 0
            lifetime_used = user.get("lifetime_used_traffic", 0) or 0
            total_traffic = max(used_traffic, lifetime_used)

            existing = self.db.get_counter_user(username)
            if existing and existing.get("last_used_traffic", 0) > 0:
                prev = existing["last_used_traffic"]
                if prev > self.TRAFFIC_THRESHOLD and total_traffic < prev * 0.1:
                    self.db.add_reset_notification(
                        admin_username, username, prev, now,
                    )
                    self.log.info("Reset detected: %s by %s (was %dMB, now %dMB)",
                                  username, admin_username,
                                  prev // (1024 * 1024),
                                  total_traffic // (1024 * 1024))

            self.db.upsert_counter_user(
                username, admin_username,
                existing["counted_at"] if existing else now,
                user.get("expire"),
                user.get("created_at", ""),
                total_traffic,
            )

    def get_report(self, admin_username: str = None, viewer: str = None) -> dict:
        if admin_username:
            totals = self.db.get_counter_totals_for_admins([admin_username])
        else:
            totals = self.db.get_all_counter_totals()
        if viewer:
            for t in totals:
                t["total_count"] = self.db.get_counter_effective_total(
                    t["admin_username"], viewer
                )
        total_count = sum(t["total_count"] for t in totals)
        return {"admins": totals, "total": total_count}

    def settle(self, admin_username: str, settled_by: str) -> int:
        total = self.db.get_counter_total(admin_username)
        settled = self.db.get_counter_settled_amount(admin_username, settled_by)
        current_view = max(0, total - settled)
        if current_view > 0:
            self.db.settle_counter(admin_username, settled_by)
            self.log.info("Counter: settled %s by %s (%d configs)",
                         admin_username, settled_by, current_view)
        return current_view

    def reset(self, admin_username: str = None):
        if admin_username:
            cursor = self.db.conn.cursor()
            cursor.execute(
                "DELETE FROM counter_users WHERE admin_username = ?", (admin_username,)
            )
            cursor.execute(
                "DELETE FROM counter_totals WHERE admin_username = ?", (admin_username,)
            )
            self.db.conn.commit()
        else:
            self.db.reset_all_counters()
