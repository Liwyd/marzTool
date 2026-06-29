import json
import logging
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    requests = None


class NodeSync:
    def __init__(self, master_url: str, node_name: str, node_token: str = None,
                 logger=None):
        self.master_url = master_url.rstrip("/")
        self.node_name = node_name
        self.node_token = node_token
        self.log = logger or logging.getLogger("node_sync")
        self._last_config_version = 0
        self._headers = {}

    def register(self) -> str | None:
        if requests is None:
            self.log.error("requests library not installed")
            return None
        try:
            resp = requests.post(
                f"{self.master_url}/api/nodes",
                json={"name": self.node_name, "url": "local"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.node_token = data["token"]
                self._headers = {"Authorization": f"Bearer {self.node_token}"}
                self.log.info("Registered with master. node_id=%d", data["node_id"])
                return self.node_token
            else:
                self.log.error("Registration failed: %d %s", resp.status_code, resp.text)
                return None
        except Exception as e:
            self.log.error("Registration error: %s", e)
            return None

    def _ensure_auth(self):
        if self.node_token and not self._headers:
            self._headers = {"Authorization": f"Bearer {self.node_token}"}

    def pull_config(self) -> dict | None:
        if requests is None or not self.node_token:
            return None
        self._ensure_auth()
        try:
            resp = requests.get(
                f"{self.master_url}/api/config",
                headers=self._headers,
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                self.log.warning("Pull config failed: %d", resp.status_code)
                return None
        except Exception as e:
            self.log.warning("Pull config error: %s", e)
            return None

    def push_data(self, data_type: str, data: dict) -> bool:
        if requests is None or not self.node_token:
            return False
        self._ensure_auth()
        try:
            resp = requests.post(
                f"{self.master_url}/api/data",
                headers=self._headers,
                json={"type": data_type, "data": data},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as e:
            self.log.warning("Push data error (%s): %s", data_type, e)
            return False

    def push_counter_data(self, counter_totals: list, report: dict):
        data = {
            "totals": counter_totals,
            "report": report,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.push_data("counter", data)

    def push_vcounter_data(self, vcounter_totals: list, report: dict):
        data = {
            "totals": vcounter_totals,
            "report": report,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.push_data("vcounter", data)

    def push_volume_data(self, disabled_count: int, limit_gb: int):
        data = {
            "disabled_count": disabled_count,
            "limit_gb": limit_gb,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.push_data("volume", data)

    def push_status(self, flow_enabled: bool, ip_limit_enabled: bool,
                    counter_enabled: bool, vcounter_enabled: bool,
                    volume_limit_enabled: bool, daemon_running: bool):
        data = {
            "flow_enabled": flow_enabled,
            "ip_limit_enabled": ip_limit_enabled,
            "counter_enabled": counter_enabled,
            "vcounter_enabled": vcounter_enabled,
            "volume_limit_enabled": volume_limit_enabled,
            "daemon_running": daemon_running,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.push_data("status", data)

    def check_config_update(self) -> dict | None:
        config = self.pull_config()
        if not config:
            return None
        remote_version = int(config.get("config_version", 0))
        if remote_version > self._last_config_version:
            self._last_config_version = remote_version
            self.log.info("Config update received (version %d)", remote_version)
            return config
        return None

    def apply_config_to_db(self, db, config: dict):
        mapping = {
            "interval": ("daemon_interval", str),
            "flow_enabled": ("flow_enabled", str),
            "flow_value": ("flow_value", str),
            "ip_limit_enabled": ("ip_limit_enabled", str),
            "counter_enabled": ("counter_enabled", str),
            "vcounter_enabled": ("vcounter_enabled", str),
            "volume_limit_enabled": ("volume_limit_enabled", str),
            "volume_limit_gb": ("volume_limit_gb", str),
            "telegram_enabled": ("telegram_enabled", str),
            "telegram_token": ("telegram_token", str),
            "telegram_admin_id": ("telegram_admin_id", str),
        }
        for key, (db_key, converter) in mapping.items():
            if key in config:
                db.set_setting(db_key, converter(config[key]))
        if "config_version" in config:
            self._last_config_version = int(config["config_version"])
        self.log.info("Config applied from master.")
