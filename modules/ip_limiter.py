import csv
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


class IPLimiter:
    def __init__(self, client, config, logger: logging.Logger = None):
        self.client = client
        self.config = config
        self.db = config.db
        self.log = logger or logging.getLogger("ip_limiter")
        self.blocked_ips_path = Path(__file__).parent.parent / "blocked_ips.csv"

    def _ensure_blocked_file(self):
        if not self.blocked_ips_path.exists():
            self.blocked_ips_path.write_text("")

    def _read_blocked_ips(self) -> list[tuple[str, int]]:
        self._ensure_blocked_file()
        entries = []
        with open(self.blocked_ips_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(",")
                    if len(parts) >= 2:
                        try:
                            entries.append((parts[0], int(parts[1])))
                        except ValueError:
                            pass
        return entries

    def _write_blocked_ips(self, entries: list[tuple[str, int]]):
        self._ensure_blocked_file()
        with open(self.blocked_ips_path, "w") as f:
            for ip, end_time in entries:
                f.write(f"{ip},{end_time}\n")

    def ban_ip(self, ip: str, email: str):
        ban_time = self.config.get_ban_time()
        ban_seconds = ban_time * 60
        ssh_port = self.config.get_ssh_port()

        end_time = int(time.time()) + ban_seconds

        blocked = self._read_blocked_ips()
        already_blocked = any(entry[0] == ip for entry in blocked)

        if not already_blocked:
            blocked.append((ip, end_time))
            self._write_blocked_ips(blocked)

        script_path = Path(__file__).parent.parent / "ipban.sh"
        if script_path.exists():
            try:
                subprocess.run(
                    ["bash", str(script_path), ip, str(ban_time), str(ssh_port)],
                    capture_output=True,
                    timeout=30,
                )
                self.log.info("IP %s banned for %s minutes (user: %s)", ip, ban_time, email)
            except Exception as e:
                self.log.error("Failed to ban IP %s: %s", ip, e)
        else:
            self._ban_iptables(ip)

    def _ban_iptables(self, ip: str):
        try:
            subprocess.run(
                ["iptables", "-C", "INPUT", "-s", ip, "-j", "DROP"],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"],
                capture_output=True,
                timeout=10,
            )
        except FileNotFoundError:
            pass

        try:
            subprocess.run(
                ["iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"],
                capture_output=True,
                timeout=10,
            )
            self.log.info("IP %s banned via iptables", ip)
        except Exception as e:
            self.log.error("Failed to ban IP %s via iptables: %s", ip, e)

    def unban_expired(self):
        blocked = self._read_blocked_ips()
        if not blocked:
            return

        current_time = int(time.time())
        remaining = []

        for ip, end_time in blocked:
            if current_time >= end_time:
                try:
                    subprocess.run(
                        ["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"],
                        capture_output=True,
                        timeout=10,
                    )
                    self.log.info("Unbanned expired IP: %s", ip)
                except Exception as e:
                    self.log.error("Failed to unban IP %s: %s", ip, e)
            else:
                remaining.append((ip, end_time))

        self._write_blocked_ips(remaining)

    def restore_bans(self):
        self._ensure_blocked_file()
        blocked = self._read_blocked_ips()
        if not blocked:
            return

        current_time = int(time.time())
        remaining = []

        for ip, end_time in blocked:
            if current_time < end_time:
                try:
                    subprocess.run(
                        ["iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"],
                        capture_output=True,
                        timeout=10,
                    )
                    self.log.info("Restored ban for IP: %s", ip)
                except Exception as e:
                    self.log.error("Failed to restore ban for IP %s: %s", ip, e)
                remaining.append((ip, end_time))

        self._write_blocked_ips(remaining)

    def get_user_ip_limit(self, email: str) -> int:
        custom = self.db.get_ip_limit(email)
        if custom is not None:
            return custom
        return self.config.get_ip_limit_all()

    def process_user_connections(self, email: str, connected_ips: list[dict]):
        limit = self.get_user_ip_limit(email)
        tracked = self.db.get_tracked_user(email)

        if not tracked:
            self.db.upsert_tracked_user(
                email,
                [{"ip": ip["ip"], "port": ip["port"], "date": ip["date"]} for ip in connected_ips],
                datetime.now(timezone.utc).isoformat(),
            )
            return

        existing_ips = tracked["ips"]
        new_ips = []

        for conn in connected_ips:
            found = False
            for i, existing in enumerate(existing_ips):
                if existing["ip"] == conn["ip"]:
                    existing_ips[i]["date"] = conn["date"]
                    found = True
                    break
            if not found:
                new_ips.append(conn)

        for new_ip in new_ips:
            if len(existing_ips) >= limit:
                self.ban_ip(new_ip["ip"], email)
                self.log.warning(
                    "User %s exceeded IP limit (%d/%d), IP %s banned",
                    email, len(existing_ips), limit, new_ip["ip"],
                )
            else:
                existing_ips.append(new_ip)

        self.db.upsert_tracked_user(
            email, existing_ips, datetime.now(timezone.utc).isoformat()
        )

    def cleanup_inactive(self, inactive_minutes: int = 5):
        cutoff = datetime.now(timezone.utc).timestamp() - (inactive_minutes * 60)
        tracked_users = self.db.get_all_tracked_users()

        for user in tracked_users:
            if user["ips"]:
                last_dates = []
                for ip in user["ips"]:
                    try:
                        d = datetime.fromisoformat(ip["date"].replace("Z", "+00:00"))
                        last_dates.append(d.timestamp())
                    except (ValueError, KeyError):
                        pass

                if last_dates and max(last_dates) < cutoff:
                    self.db.delete_tracked_user(user["email"])
                    self.log.info("Cleaned up inactive user: %s", user["email"])

    def set_all_users_limit(self, limit: int):
        self.config.set_ip_limit_all(limit)
        users = self.client.get_all_users()
        for user in users:
            self.db.set_ip_limit(user["username"], limit)
        self.log.info("Set IP limit to %d for all %d users", limit, len(users))

    def process_cycle(self, inactive_minutes: int = 5, users: list = None) -> tuple[int, int, list, list]:
        if users is None:
            users = self.client.get_all_users()
        tracked = self.db.get_all_tracked_users()
        tracked_emails = {t["email"] for t in tracked}

        new_users = []
        for user in users:
            email = user["username"]
            if email not in tracked_emails:
                self.db.set_ip_limit(email, self.config.get_ip_limit_all())
                self.db.upsert_tracked_user(email, [], datetime.now(timezone.utc).isoformat())
                new_users.append(email)

        self.cleanup_inactive(inactive_minutes)
        self.unban_expired()

        return len(users), len(new_users), [], []

    def run_once(self, inactive_minutes: int = 5) -> tuple[int, int, list, list]:
        self.log.info("IP limiter: checking users")
        return self.process_cycle(inactive_minutes)
