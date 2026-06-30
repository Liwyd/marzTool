import logging
from datetime import datetime, timezone


class VCounter:
    def __init__(self, client, db, logger: logging.Logger = None):
        self.client = client
        self.db = db
        self.log = logger or logging.getLogger("vcounter")

    def sync(self, users: list = None):
        if users is None:
            users = self.client.get_all_users()

        admin_totals = {}

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

            if admin_username not in admin_totals:
                admin_totals[admin_username] = 0
            admin_totals[admin_username] += data_limit

        for admin_username, total_bytes in admin_totals.items():
            self.db.set_vcounter_total(admin_username, total_bytes)

        self.log.info(
            "VCounter sync complete. %d admins, %d configs with data_limit.",
            len(admin_totals),
            sum(1 for u in (users or []) if (u.get("data_limit") or 0) > 0),
        )

    def get_report(self, admin_username=None, viewer: str = None) -> dict:
        if admin_username:
            if isinstance(admin_username, str):
                admin_username = [admin_username]
            totals = self.db.get_vcounter_totals_for_admins(admin_username)
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
