import json
import os
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "marztool.db"


class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self.conn = sqlite3.connect(self.db_path)
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_ip_limits (
                email TEXT PRIMARY KEY,
                limit_count INTEGER NOT NULL DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_users (
                email TEXT PRIMARY KEY,
                ips TEXT NOT NULL DEFAULT '[]',
                last_seen TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS counter_users (
                username TEXT PRIMARY KEY,
                admin_username TEXT NOT NULL,
                counted_at TEXT NOT NULL,
                last_expire INTEGER,
                last_created_at TEXT,
                last_used_traffic INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS counter_totals (
                admin_username TEXT PRIMARY KEY,
                total_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reset_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_username TEXT NOT NULL,
                username TEXT NOT NULL,
                prev_traffic_bytes INTEGER DEFAULT 0,
                reset_at TEXT NOT NULL,
                notified INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sub_admins (
                telegram_id INTEGER PRIMARY KEY,
                allowed_admins TEXT NOT NULL DEFAULT '[]'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exempt_users (
                username TEXT PRIMARY KEY,
                added_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS volume_limit_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                admin_username TEXT,
                used_traffic_bytes INTEGER DEFAULT 0,
                disabled_at TEXT NOT NULL,
                notified INTEGER DEFAULT 0,
                chat_id INTEGER,
                message_id INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vcounter_users (
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                admin_username TEXT NOT NULL,
                initial_data_limit INTEGER DEFAULT 0,
                counted_traffic INTEGER DEFAULT 0,
                prev_traffic INTEGER DEFAULT 0,
                last_check TEXT,
                PRIMARY KEY (username, created_at)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vcounter_totals (
                admin_username TEXT PRIMARY KEY,
                total_volume_bytes INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vcounter_settlements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_username TEXT NOT NULL,
                settled_by TEXT NOT NULL,
                amount_bytes INTEGER NOT NULL DEFAULT 0,
                settled_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS counter_settlements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_username TEXT NOT NULL,
                settled_by TEXT NOT NULL,
                amount_count INTEGER NOT NULL DEFAULT 0,
                settled_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vcounter_sub_admins (
                telegram_id INTEGER PRIMARY KEY,
                allowed_admins TEXT NOT NULL DEFAULT '[]'
            )
        """)
        self.conn.commit()

    def get_setting(self, key: str) -> str | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    def get_all_settings(self) -> dict:
        cursor = self.conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_ip_limit(self, email: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT limit_count FROM user_ip_limits WHERE email = ?", (email,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def set_ip_limit(self, email: str, limit_count: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO user_ip_limits (email, limit_count) VALUES (?, ?)",
            (email, limit_count),
        )
        self.conn.commit()

    def get_all_ip_limits(self) -> dict:
        cursor = self.conn.cursor()
        cursor.execute("SELECT email, limit_count FROM user_ip_limits")
        return {row[0]: row[1] for row in cursor.fetchall()}

    def delete_ip_limit(self, email: str):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM user_ip_limits WHERE email = ?", (email,))
        self.conn.commit()

    def get_tracked_user(self, email: str) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT email, ips, last_seen FROM tracked_users WHERE email = ?",
            (email,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"email": row[0], "ips": json.loads(row[1]), "last_seen": row[2]}

    def upsert_tracked_user(self, email: str, ips: list, last_seen: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO tracked_users (email, ips, last_seen) VALUES (?, ?, ?)",
            (email, json.dumps(ips), last_seen),
        )
        self.conn.commit()

    def delete_tracked_user(self, email: str):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tracked_users WHERE email = ?", (email,))
        self.conn.commit()

    def get_all_tracked_users(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT email, ips, last_seen FROM tracked_users")
        return [
            {"email": row[0], "ips": json.loads(row[1]), "last_seen": row[2]}
            for row in cursor.fetchall()
        ]

    def get_counter_user(self, username: str) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT username, admin_username, counted_at, last_expire, last_created_at, last_used_traffic "
            "FROM counter_users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "username": row[0], "admin_username": row[1], "counted_at": row[2],
            "last_expire": row[3], "last_created_at": row[4], "last_used_traffic": row[5],
        }

    def upsert_counter_user(self, username: str, admin_username: str, counted_at: str,
                             last_expire, last_created_at: str, last_used_traffic: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO counter_users "
            "(username, admin_username, counted_at, last_expire, last_created_at, last_used_traffic) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (username, admin_username, counted_at, last_expire, last_created_at, last_used_traffic),
        )
        self.conn.commit()

    def get_counter_total(self, admin_username: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT total_count FROM counter_totals WHERE admin_username = ?",
            (admin_username,),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def set_counter_total(self, admin_username: str, total_count: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO counter_totals (admin_username, total_count) VALUES (?, ?)",
            (admin_username, total_count),
        )
        self.conn.commit()

    def increment_counter_total(self, admin_username: str, amount: int = 1):
        current = self.get_counter_total(admin_username)
        self.set_counter_total(admin_username, current + amount)

    def get_all_counter_totals(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT admin_username, total_count FROM counter_totals ORDER BY total_count DESC")
        return [{"admin_username": row[0], "total_count": row[1]} for row in cursor.fetchall()]

    def get_counter_totals_for_admins(self, admin_usernames: list[str]) -> list:
        if not admin_usernames:
            return []
        placeholders = ",".join("?" for _ in admin_usernames)
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT admin_username, total_count FROM counter_totals "
            f"WHERE admin_username IN ({placeholders}) ORDER BY total_count DESC",
            admin_usernames,
        )
        return [{"admin_username": row[0], "total_count": row[1]} for row in cursor.fetchall()]

    def reset_all_counters(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM counter_users")
        cursor.execute("DELETE FROM counter_totals")
        self.conn.commit()

    def add_reset_notification(self, admin_username: str, username: str,
                                prev_traffic_bytes: int, reset_at: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO reset_notifications (admin_username, username, prev_traffic_bytes, reset_at) "
            "VALUES (?, ?, ?, ?)",
            (admin_username, username, prev_traffic_bytes, reset_at),
        )
        self.conn.commit()

    def get_pending_reset_notifications(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, admin_username, username, prev_traffic_bytes, reset_at "
            "FROM reset_notifications WHERE notified = 0"
        )
        return [
            {"id": row[0], "admin_username": row[1], "username": row[2],
             "prev_traffic_bytes": row[3], "reset_at": row[4]}
            for row in cursor.fetchall()
        ]

    def clear_reset_notification(self, notif_id: int):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE reset_notifications SET notified = 1 WHERE id = ?", (notif_id,))
        self.conn.commit()

    def add_sub_admin(self, telegram_id: int, allowed_admins: list[str]):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO sub_admins (telegram_id, allowed_admins) VALUES (?, ?)",
            (telegram_id, json.dumps(allowed_admins)),
        )
        self.conn.commit()

    def remove_sub_admin(self, telegram_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM sub_admins WHERE telegram_id = ?", (telegram_id,))
        self.conn.commit()

    def get_sub_admin(self, telegram_id: int) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT telegram_id, allowed_admins FROM sub_admins WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"telegram_id": row[0], "allowed_admins": row[1]}

    def get_all_sub_admins(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT telegram_id, allowed_admins FROM sub_admins")
        return [{"telegram_id": row[0], "allowed_admins": row[1]} for row in cursor.fetchall()]

    def update_sub_admin_scope(self, telegram_id: int, allowed_admins: list[str]):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE sub_admins SET allowed_admins = ? WHERE telegram_id = ?",
            (json.dumps(allowed_admins), telegram_id),
        )
        self.conn.commit()

    def is_exempt(self, username: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM exempt_users WHERE username = ?", (username,))
        return cursor.fetchone() is not None

    def add_exempt(self, username: str, added_at: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO exempt_users (username, added_at) VALUES (?, ?)",
            (username, added_at),
        )
        self.conn.commit()

    def remove_exempt(self, username: str):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM exempt_users WHERE username = ?", (username,))
        self.conn.commit()

    def get_all_exempt_users(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT username, added_at FROM exempt_users")
        return [{"username": row[0], "added_at": row[1]} for row in cursor.fetchall()]

    def add_volume_notification(self, username: str, admin_username: str,
                                used_traffic_bytes: int, disabled_at: str,
                                chat_id: int = None, message_id: int = None):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO volume_limit_notifications "
            "(username, admin_username, used_traffic_bytes, disabled_at, chat_id, message_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (username, admin_username, used_traffic_bytes, disabled_at, chat_id, message_id),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_notification_message(self, notif_id: int, chat_id: int, message_id: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE volume_limit_notifications SET chat_id = ?, message_id = ?, notified = 1 WHERE id = ?",
            (chat_id, message_id, notif_id),
        )
        self.conn.commit()

    def get_volume_notification(self, notif_id: int) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, username, admin_username, used_traffic_bytes, disabled_at, chat_id, message_id "
            "FROM volume_limit_notifications WHERE id = ?",
            (notif_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "username": row[1], "admin_username": row[2],
            "used_traffic_bytes": row[3], "disabled_at": row[4],
            "chat_id": row[5], "message_id": row[6],
        }

    def was_already_notified_volume(self, username: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM volume_limit_notifications WHERE username = ? AND notified = 1",
            (username,),
        )
        return cursor.fetchone() is not None

    def get_vcounter_user(self, username: str, created_at: str) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT username, created_at, admin_username, initial_data_limit, "
            "counted_traffic, prev_traffic, last_check "
            "FROM vcounter_users WHERE username = ? AND created_at = ?",
            (username, created_at),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "username": row[0], "created_at": row[1], "admin_username": row[2],
            "initial_data_limit": row[3], "counted_traffic": row[4],
            "prev_traffic": row[5], "last_check": row[6],
        }

    def get_vcounter_user_by_username(self, username: str) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT username, created_at, admin_username, initial_data_limit, "
            "counted_traffic, prev_traffic, last_check "
            "FROM vcounter_users WHERE username = ? ORDER BY created_at DESC LIMIT 1",
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "username": row[0], "created_at": row[1], "admin_username": row[2],
            "initial_data_limit": row[3], "counted_traffic": row[4],
            "prev_traffic": row[5], "last_check": row[6],
        }

    def upsert_vcounter_user(self, username: str, created_at: str, admin_username: str,
                              initial_data_limit: int, counted_traffic: int,
                              prev_traffic: int, last_check: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO vcounter_users "
            "(username, created_at, admin_username, initial_data_limit, counted_traffic, "
            "prev_traffic, last_check) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, created_at, admin_username, initial_data_limit,
             counted_traffic, prev_traffic, last_check),
        )
        self.conn.commit()

    def get_vcounter_total(self, admin_username: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT total_volume_bytes FROM vcounter_totals WHERE admin_username = ?",
            (admin_username,),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def set_vcounter_total(self, admin_username: str, total_bytes: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO vcounter_totals (admin_username, total_volume_bytes) VALUES (?, ?)",
            (admin_username, total_bytes),
        )
        self.conn.commit()

    def add_vcounter_volume(self, admin_username: str, volume_bytes: int):
        current = self.get_vcounter_total(admin_username)
        self.set_vcounter_total(admin_username, current + volume_bytes)

    def get_all_vcounter_totals(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT admin_username, total_volume_bytes FROM vcounter_totals ORDER BY total_volume_bytes DESC")
        return [{"admin_username": row[0], "total_volume_bytes": row[1]} for row in cursor.fetchall()]

    def get_vcounter_totals_for_admins(self, admin_usernames: list[str]) -> list:
        if not admin_usernames:
            return []
        placeholders = ",".join("?" for _ in admin_usernames)
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT admin_username, total_volume_bytes FROM vcounter_totals "
            f"WHERE admin_username IN ({placeholders}) ORDER BY total_volume_bytes DESC",
            admin_usernames,
        )
        return [{"admin_username": row[0], "total_volume_bytes": row[1]} for row in cursor.fetchall()]

    def reset_vcounter_for_admin(self, admin_username: str):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM vcounter_users WHERE admin_username = ?", (admin_username,))
        cursor.execute("DELETE FROM vcounter_totals WHERE admin_username = ?", (admin_username,))
        self.conn.commit()

    def settle_vcounter(self, admin_username: str, settled_by: str):
        from datetime import datetime, timezone
        total = self.get_vcounter_total(admin_username)
        settled = self.get_vcounter_settled_amount(admin_username, settled_by)
        current_view = max(0, total - settled)
        if current_view > 0:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO vcounter_settlements (admin_username, settled_by, amount_bytes, settled_at) "
                "VALUES (?, ?, ?, ?)",
                (admin_username, settled_by, current_view, datetime.now(timezone.utc).isoformat()),
            )
            self.conn.commit()

    def get_vcounter_settled_amount(self, admin_username: str, settled_by: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(amount_bytes), 0) FROM vcounter_settlements "
            "WHERE admin_username = ? AND settled_by = ?",
            (admin_username, settled_by),
        )
        return cursor.fetchone()[0]

    def get_vcounter_effective_total(self, admin_username: str, viewer: str) -> int:
        total = self.get_vcounter_total(admin_username)
        settled = self.get_vcounter_settled_amount(admin_username, viewer)
        return max(0, total - settled)

    def get_vcounter_settlements(self, admin_username: str = None) -> list:
        cursor = self.conn.cursor()
        if admin_username:
            cursor.execute(
                "SELECT id, admin_username, settled_by, amount_bytes, settled_at "
                "FROM vcounter_settlements WHERE admin_username = ? ORDER BY settled_at DESC",
                (admin_username,),
            )
        else:
            cursor.execute(
                "SELECT id, admin_username, settled_by, amount_bytes, settled_at "
                "FROM vcounter_settlements ORDER BY settled_at DESC"
            )
        return [
            {"id": row[0], "admin_username": row[1], "settled_by": row[2],
             "amount_bytes": row[3], "settled_at": row[4]}
            for row in cursor.fetchall()
        ]

    def settle_counter(self, admin_username: str, settled_by: str):
        from datetime import datetime, timezone
        total = self.get_counter_total(admin_username)
        settled = self.get_counter_settled_amount(admin_username, settled_by)
        current_view = max(0, total - settled)
        if current_view > 0:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO counter_settlements (admin_username, settled_by, amount_count, settled_at) "
                "VALUES (?, ?, ?, ?)",
                (admin_username, settled_by, current_view, datetime.now(timezone.utc).isoformat()),
            )
            self.conn.commit()

    def get_counter_settled_amount(self, admin_username: str, settled_by: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(amount_count), 0) FROM counter_settlements "
            "WHERE admin_username = ? AND settled_by = ?",
            (admin_username, settled_by),
        )
        return cursor.fetchone()[0]

    def get_counter_effective_total(self, admin_username: str, viewer: str) -> int:
        total = self.get_counter_total(admin_username)
        settled = self.get_counter_settled_amount(admin_username, viewer)
        return max(0, total - settled)

    def get_counter_settlements(self, admin_username: str = None) -> list:
        cursor = self.conn.cursor()
        if admin_username:
            cursor.execute(
                "SELECT id, admin_username, settled_by, amount_count, settled_at "
                "FROM counter_settlements WHERE admin_username = ? ORDER BY settled_at DESC",
                (admin_username,),
            )
        else:
            cursor.execute(
                "SELECT id, admin_username, settled_by, amount_count, settled_at "
                "FROM counter_settlements ORDER BY settled_at DESC"
            )
        return [
            {"id": row[0], "admin_username": row[1], "settled_by": row[2],
             "amount_count": row[3], "settled_at": row[4]}
            for row in cursor.fetchall()
        ]

    def add_vcounter_sub_admin(self, telegram_id: int, allowed_admins: list[str]):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO vcounter_sub_admins (telegram_id, allowed_admins) VALUES (?, ?)",
            (telegram_id, json.dumps(allowed_admins)),
        )
        self.conn.commit()

    def remove_vcounter_sub_admin(self, telegram_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM vcounter_sub_admins WHERE telegram_id = ?", (telegram_id,))
        self.conn.commit()

    def get_vcounter_sub_admin(self, telegram_id: int) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT telegram_id, allowed_admins FROM vcounter_sub_admins WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"telegram_id": row[0], "allowed_admins": row[1]}

    def get_all_vcounter_sub_admins(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT telegram_id, allowed_admins FROM vcounter_sub_admins")
        return [{"telegram_id": row[0], "allowed_admins": row[1]} for row in cursor.fetchall()]

    def update_vcounter_sub_admin_scope(self, telegram_id: int, allowed_admins: list[str]):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE vcounter_sub_admins SET allowed_admins = ? WHERE telegram_id = ?",
            (json.dumps(allowed_admins), telegram_id),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
