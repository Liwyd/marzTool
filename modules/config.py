from .database import Database


class Config:
    def __init__(self, db: Database):
        self.db = db

    def get_server_url(self) -> str | None:
        return self.db.get_setting("server_url")

    def set_server_url(self, url: str):
        self.db.set_setting("server_url", url)

    def get_username(self) -> str | None:
        return self.db.get_setting("username")

    def set_username(self, username: str):
        self.db.set_setting("username", username)

    def get_password(self) -> str | None:
        return self.db.get_setting("password")

    def set_password(self, password: str):
        self.db.set_setting("password", password)

    def get_flow_value(self) -> str:
        val = self.db.get_setting("flow_value")
        return val if val is not None else "xtls-rprx-vision"

    def set_flow_value(self, value: str):
        self.db.set_setting("flow_value", value)

    def get_ip_limit_all(self) -> int:
        val = self.db.get_setting("ip_limit_all")
        return int(val) if val is not None else 1

    def set_ip_limit_all(self, limit: int):
        self.db.set_setting("ip_limit_all", str(limit))

    def get_ip_limit_enabled(self) -> bool:
        val = self.db.get_setting("ip_limit_enabled")
        return val == "true" if val is not None else False

    def set_ip_limit_enabled(self, enabled: bool):
        self.db.set_setting("ip_limit_enabled", "true" if enabled else "false")

    def get_flow_enabled(self) -> bool:
        val = self.db.get_setting("flow_enabled")
        return val == "true" if val is not None else False

    def set_flow_enabled(self, enabled: bool):
        self.db.set_setting("flow_enabled", "true" if enabled else "false")

    def get_daemon_interval(self) -> int:
        val = self.db.get_setting("daemon_interval")
        return int(val) if val is not None else 20

    def set_daemon_interval(self, seconds: int):
        self.db.set_setting("daemon_interval", str(seconds))

    def get_telegram_enabled(self) -> bool:
        val = self.db.get_setting("telegram_enabled")
        return val == "true" if val is not None else False

    def set_telegram_enabled(self, enabled: bool):
        self.db.set_setting("telegram_enabled", "true" if enabled else "false")

    def get_counter_enabled(self) -> bool:
        val = self.db.get_setting("counter_enabled")
        return val == "true" if val is not None else False

    def set_counter_enabled(self, enabled: bool):
        if enabled:
            self.db.set_setting("vcounter_enabled", "false")
        self.db.set_setting("counter_enabled", "true" if enabled else "false")

    def get_vcounter_enabled(self) -> bool:
        val = self.db.get_setting("vcounter_enabled")
        return val == "true" if val is not None else False

    def set_vcounter_enabled(self, enabled: bool):
        if enabled:
            self.db.set_setting("counter_enabled", "false")
        self.db.set_setting("vcounter_enabled", "true" if enabled else "false")

    def get_telegram_token(self) -> str | None:
        return self.db.get_setting("telegram_token")

    def set_telegram_token(self, token: str):
        self.db.set_setting("telegram_token", token)

    def get_telegram_admin_id(self) -> str | None:
        return self.db.get_setting("telegram_admin_id")

    def set_telegram_admin_id(self, admin_id: str):
        self.db.set_setting("telegram_admin_id", admin_id)

    def get_volume_limit_enabled(self) -> bool:
        val = self.db.get_setting("volume_limit_enabled")
        return val == "true" if val is not None else False

    def set_volume_limit_enabled(self, enabled: bool):
        self.db.set_setting("volume_limit_enabled", "true" if enabled else "false")

    def get_volume_limit_gb(self) -> int:
        val = self.db.get_setting("volume_limit_gb")
        return int(val) if val is not None else 250

    def set_volume_limit_gb(self, gb: int):
        self.db.set_setting("volume_limit_gb", str(gb))

    def get_ban_time(self) -> int:
        val = self.db.get_setting("ban_time")
        return int(val) if val is not None else 4

    def set_ban_time(self, minutes: int):
        self.db.set_setting("ban_time", str(minutes))

    def get_ssh_port(self) -> int:
        val = self.db.get_setting("ssh_port")
        return int(val) if val is not None else 22

    def set_ssh_port(self, port: int):
        self.db.set_setting("ssh_port", str(port))

    def get_master_enabled(self) -> bool:
        val = self.db.get_setting("master_enabled")
        return val == "true" if val is not None else False

    def set_master_enabled(self, enabled: bool):
        self.db.set_setting("master_enabled", "true" if enabled else "false")

    def get_master_port(self) -> int:
        val = self.db.get_setting("master_port")
        return int(val) if val is not None else 8888

    def set_master_port(self, port: int):
        self.db.set_setting("master_port", str(port))

    def get_node_enabled(self) -> bool:
        val = self.db.get_setting("node_enabled")
        return val == "true" if val is not None else False

    def set_node_enabled(self, enabled: bool):
        self.db.set_setting("node_enabled", "true" if enabled else "false")

    def get_node_name(self) -> str | None:
        return self.db.get_setting("node_name")

    def set_node_name(self, name: str):
        self.db.set_setting("node_name", name)

    def get_node_token(self) -> str | None:
        return self.db.get_setting("node_token")

    def set_node_token(self, token: str):
        self.db.set_setting("node_token", token)

    def get_master_url(self) -> str | None:
        return self.db.get_setting("master_url")

    def set_master_url(self, url: str):
        self.db.set_setting("master_url", url)

    def get_all_config(self) -> dict:
        return self.db.get_all_settings()

    def has_credentials(self) -> bool:
        return (
            self.get_server_url() is not None
            and self.get_username() is not None
            and self.get_password() is not None
        )
