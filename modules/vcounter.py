import logging
from datetime import datetime, timezone


class VCounter:
    TRAFFIC_THRESHOLD = 500 * 1024 * 1024

    def __init__(self, client, db, logger: logging.Logger = None):
        self.client = client
        self.db = db
        self.log = logger or logging.getLogger("vcounter")

    def sync(self, users: list = None):
        if users is None:
            users = self.client.get_all_users()
        now = datetime.now(timezone.utc).isoformat()
        panel_usernames = set()

        for user in users:
            username = user.get("username", "")
            if not username:
                continue
            admin = user.get("admin")
            if not admin or not admin.get("username"):
                continue
            admin_username = admin["username"]

            data_limit = user.get("data_limit") or 0
            if data_limit == 0:
                continue

            used_traffic = user.get("used_traffic", 0) or 0
            lifetime_used = user.get("lifetime_used_traffic", 0) or 0
            total_traffic = max(used_traffic, lifetime_used)
            created_at = user.get("created_at", "")

            existing = self.db.get_vcounter_user(username, created_at)

            if not existing:
                prev = self.db.get_vcounter_user_by_username(username)
                if prev and prev.get("created_at", "") != created_at:
                    self._count_entry(prev, prev.get("prev_traffic", 0), now)
                    self.log.info(
                        "VCounter: finalized old %s (admin=%s) — recreated",
                        username, admin_username,
                    )
                self.db.upsert_vcounter_user(
                    username, created_at, admin_username,
                    data_limit, 0, total_traffic, now,
                )
                panel_usernames.add(username)
                continue

            prev_traffic = existing.get("prev_traffic", 0)
            counted_traffic = existing.get("counted_traffic", 0)

            if total_traffic < prev_traffic * 0.1 and prev_traffic >= self.TRAFFIC_THRESHOLD:
                self._count_entry(existing, prev_traffic, now)
                self.log.info(
                    "VCounter: counted %s (admin=%s) — reset detected",
                    username, admin_username,
                )
                self.db.upsert_vcounter_user(
                    username, now, admin_username,
                    data_limit, 0, total_traffic, now,
                )
                panel_usernames.add(username)
                continue

            delta = total_traffic - counted_traffic
            if delta >= self.TRAFFIC_THRESHOLD:
                self.db.add_vcounter_volume(admin_username, delta)
                self.db.upsert_vcounter_user(
                    username, created_at, admin_username,
                    data_limit, total_traffic, total_traffic, now,
                )
                self.log.info(
                    "VCounter: +%dMB for %s (admin=%s) — total now tracked",
                    delta // (1024 * 1024), username, admin_username,
                )
            else:
                self.db.upsert_vcounter_user(
                    username, created_at, admin_username,
                    data_limit, counted_traffic, total_traffic, now,
                )

            panel_usernames.add(username)

        self.log.info("VCounter sync complete. %d configs active.", len(panel_usernames))

    def _count_entry(self, entry: dict, traffic: int, now: str):
        admin_username = entry.get("admin_username", "")
        data_limit = entry.get("initial_data_limit", 0)
        counted_traffic = entry.get("counted_traffic", 0)
        remaining = traffic - counted_traffic
        if remaining > 0:
            self.db.add_vcounter_volume(admin_username, remaining)
        self.db.upsert_vcounter_user(
            entry["username"], entry["created_at"], admin_username,
            data_limit, traffic, traffic, now,
        )

    def get_report(self, admin_username: str = None, viewer: str = None) -> dict:
        if admin_username:
            totals = self.db.get_vcounter_totals_for_admins([admin_username])
        else:
            totals = self.db.get_all_vcounter_totals()
        if viewer:
            for t in totals:
                t["total_volume_bytes"] = self.db.get_vcounter_effective_total(
                    t["admin_username"], viewer
                )
        total_bytes = sum(t["total_volume_bytes"] for t in totals)
        return {"admins": totals, "total_bytes": total_bytes}

    def settle(self, admin_username: str, settled_by: str) -> int:
        total = self.db.get_vcounter_total(admin_username)
        settled = self.db.get_vcounter_settled_amount(admin_username, settled_by)
        current_view = max(0, total - settled)
        if current_view > 0:
            self.db.settle_vcounter(admin_username, settled_by)
            self.log.info("VCounter: settled %s by %s (%d MB)",
                         admin_username, settled_by, current_view // (1024 * 1024))
        return current_view
