import os
import sys
import time
from pathlib import Path

from .api_client import MarzbanClient
from .config import Config
from .database import Database
from .daemon import (
    daemon_pid,
    stop_daemon,
    view_logs,
    spawn_daemon,
    _make_logger,
)
from .flow_setter import FlowSetter
from .ip_limiter import IPLimiter
from .telegram_bot import TelegramBot


_C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "dim": "\033[2m",
    "magenta": "\033[35m",
    "white": "\033[97m",
}


def c(name: str, text: str) -> str:
    return f"{_C.get(name, '')}{text}{_C['reset']}"


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


class TUI:
    def __init__(self):
        self.db = Database()
        self.config = Config(self.db)
        self.client = None
        self.telegram = TelegramBot(self.config)

    def _banner(self):
        clear_screen()
        from modules.web_daemon import web_daemon_pid, web_daemon_port
        pid = daemon_pid()
        web_pid = web_daemon_pid()
        status = (
            c("green", f"RUNNING  (PID {pid})")
            if pid else
            c("dim", "stopped")
        )
        web_port = web_daemon_port()
        web_status = (
            c("green", f"ON  http://0.0.0.0:{web_port}")
            if web_pid else
            c("dim", "OFF")
        )

        flow_val = self.config.get_flow_value()
        if self.config.get_flow_enabled():
            flow_display = c("green", f"ON ({flow_val})") if flow_val else c("green", "ON (unset)")
        else:
            flow_display = c("dim", "OFF")

        ip_status = c("green", "ON") if self.config.get_ip_limit_enabled() else c("dim", "OFF")
        tg_status = c("green", "ON") if self.config.get_telegram_enabled() else c("dim", "OFF")
        ct_status = c("green", "ON") if self.config.get_counter_enabled() else c("dim", "OFF")
        vl_gb = self.config.get_volume_limit_gb()
        vl_status = c("green", f"ON ({vl_gb}GB)") if self.config.get_volume_limit_enabled() else c("dim", "OFF")
        vc_status = c("green", "ON") if self.config.get_vcounter_enabled() else c("dim", "OFF")

        print(c("bold", c("cyan", "=" * 65)))
        print(c("bold", c("cyan", "  MarzTool - Marzban Management Suite")))
        print(c("bold", c("cyan", "=" * 65)))
        print(f"  Daemon  : {status}")
        print(f"  Web UI  : {web_status}")
        print(f"  Flow    : {flow_display}")
        print(f"  IP Limit: {ip_status}    Telegram: {tg_status}")
        print(f"  Traffic : {vl_status}")
        ct_on = self.config.get_counter_enabled()
        vc_on = self.config.get_vcounter_enabled()
        if ct_on:
            print(f"  Mode: {c('green', 'User Counter')}")
        elif vc_on:
            print(f"  Mode: {c('green', 'Bandwidth Tracker')}")
        else:
            print(f"  Counter: {ct_status}    Bandwidth: {vc_status}")
        print(c("dim", f"  Server  : {self.config.get_server_url() or 'not set'}"))
        print(c("bold", c("cyan", "-" * 65)))

    def _ask(self, prompt: str, default: str = "") -> str:
        try:
            display_default = f" [{default}]" if default else ""
            val = input(f"  {prompt}{display_default}: ").strip()
            return val if val else default
        except (EOFError, KeyboardInterrupt):
            print()
            return default

    def _menu(self, options: list[tuple[str, str]]) -> int:
        display_to_idx = []
        idx = 0
        for label, key in options:
            if key == "---":
                print(f"  {c('dim', '─' * 40)}")
            else:
                display_to_idx.append(idx)
                print(f"  {c('cyan', str(len(display_to_idx)))}.  {label}")
            idx += 1
        print()
        try:
            raw = input("  Choose: ").strip()
            n = int(raw)
            if 1 <= n <= len(display_to_idx):
                return display_to_idx[n - 1]
        except (ValueError, EOFError, KeyboardInterrupt):
            pass
        return -1

    def _ensure_client(self) -> bool:
        url = self.config.get_server_url()
        username = self.config.get_username()
        password = self.config.get_password()

        if not url or not username or not password:
            print(c("yellow", "\n  Credentials not configured. Please setup first."))
            return False

        try:
            self.client = MarzbanClient(url)
            self.client.login(username, password)
            return True
        except Exception as e:
            print(c("red", f"\n  Connection failed: {e}"))
            return False

    def _setup_wizard(self):
        print(c("bold", c("cyan", "\n  === Setup Wizard ===")))

        saved_url = self.config.get_server_url() or ""
        saved_user = self.config.get_username() or ""
        saved_pass = self.config.get_password() or ""

        url = self._ask("Panel URL (e.g. https://example.com:443)", saved_url)
        username = self._ask("Admin username", saved_user)
        password = self._ask("Admin password", saved_pass)

        self.config.set_server_url(url)
        self.config.set_username(username)
        self.config.set_password(password)

        print(c("green", "\n  Credentials saved."))

    def _setup_telegram(self):
        print(c("bold", c("cyan", "\n  === Telegram Bot Setup ===")))

        tg_enabled = self.config.get_telegram_enabled()
        current = "ON" if tg_enabled else "OFF"
        print(f"  Current status: {c('green' if tg_enabled else 'dim', current)}")
        enable = self._ask("Enable Telegram? (y/n)", "y" if tg_enabled else "n")
        self.config.set_telegram_enabled(enable.lower() == "y")

        if enable.lower() == "y":
            saved_token = self.config.get_telegram_token() or ""
            saved_admin = self.config.get_telegram_admin_id() or ""

            token = self._ask("Bot token", saved_token)
            admin_id = self._ask("Admin chat ID", saved_admin)

            self.config.set_telegram_token(token)
            self.config.set_telegram_admin_id(admin_id)

            if self.telegram.app:
                self.telegram.stop()
            self.telegram.start()

            print(c("green", "\n  Telegram bot configured."))
        else:
            self.telegram.stop()

    def _test_telegram(self):
        print(c("bold", c("cyan", "\n  === Test Telegram Connection ===")))
        print("  Testing API connectivity, bot token, admin chat, and sending test message...")
        print()
        ok, msg = self.telegram.test_connection()
        if ok:
            print(c("green", f"  SUCCESS: {msg}"))
        else:
            print(c("red", f"  FAILED: {msg}"))
        print()

    def _setup_master_node(self):
        print(c("bold", c("cyan", "\n  === Master / Node Configuration ===")))
        print()
        print("  This server can run as:")
        print(f"  {c('cyan', '1')}.  Master - runs API server, aggregates data from nodes")
        print(f"  {c('cyan', '2')}.  Node - connects to master, receives config, pushes data")
        print(f"  {c('cyan', '3')}.  Standalone (default) - no master/node, runs independently")
        print(f"  {c('cyan', '4')}.  View current mode")
        print(f"  {c('cyan', '5')}.  Back")
        print()

        try:
            choice = int(input("  Choose: ").strip())
        except (ValueError, EOFError, KeyboardInterrupt):
            return

        if choice == 1:
            self._setup_master()
        elif choice == 2:
            self._setup_node()
        elif choice == 3:
            self.config.set_master_enabled(False)
            self.config.set_node_enabled(False)
            print(c("green", "\n  Running in standalone mode."))
        elif choice == 4:
            self._show_master_node_status()

    def _setup_master(self):
        print(c("bold", c("cyan", "\n  === Setup Master Mode ===")))
        print("  Master runs an HTTP API server that nodes connect to.")
        print("  Master aggregates counter/bandwidth/traffic data from all nodes.")
        print()

        enabled = self.config.get_master_enabled()
        current = "ON" if enabled else "OFF"
        print(f"  Current status: {c('green' if enabled else 'dim', current)}")

        enable = self._ask("Enable master mode? (y/n)", "y" if enabled else "n")
        if enable.lower() == "y":
            port = self._ask("API port", str(self.config.get_master_port()))
            self.config.set_master_port(int(port))
            self.config.set_master_enabled(True)
            self.config.set_node_enabled(False)
            print(c("green", f"\n  Master mode enabled on port {port}."))
            print(c("dim", "  Start the daemon to activate the master API."))
        else:
            self.config.set_master_enabled(False)
            print(c("green", "\n  Master mode disabled."))

    def _setup_node(self):
        print(c("bold", c("cyan", "\n  === Setup Node Mode ===")))
        print("  Node connects to a master server for config and pushes data.")
        print()

        enabled = self.config.get_node_enabled()
        current = "ON" if enabled else "OFF"
        print(f"  Current status: {c('green' if enabled else 'dim', current)}")

        enable = self._ask("Enable node mode? (y/n)", "y" if enabled else "n")
        if enable.lower() == "y":
            saved_url = self.config.get_master_url() or ""
            saved_name = self.config.get_node_name() or ""

            url = self._ask("Master URL (e.g. http://master-ip:8888)", saved_url)
            name = self._ask("Node name (for identification)", saved_name or "node1")

            self.config.set_master_url(url)
            self.config.set_node_name(name)
            self.config.set_node_enabled(True)
            self.config.set_master_enabled(False)
            print(c("green", f"\n  Node mode enabled. Name: {name}"))
            print(c("dim", "  Node will register with master on first daemon start."))
        else:
            self.config.set_node_enabled(False)
            print(c("green", "\n  Node mode disabled."))

    def _show_master_node_status(self):
        print(c("bold", c("cyan", "\n  === Master / Node Status ===")))
        master_on = self.config.get_master_enabled()
        node_on = self.config.get_node_enabled()

        if master_on:
            print(f"  Mode: {c('green', 'MASTER')}")
            print(f"  API Port: {self.config.get_master_port()}")
            nodes = self.db.get_all_nodes()
            print(f"  Registered nodes: {len(nodes)}")
            for n in nodes:
                status = c("dim", "offline")
                if n["last_seen"]:
                    try:
                        from datetime import datetime, timezone
                        seen = datetime.fromisoformat(n["last_seen"])
                        delta = datetime.now(timezone.utc) - seen
                        if delta.total_seconds() < 120:
                            status = c("green", "online")
                    except Exception:
                        pass
                print(f"    - {n['name']} (id={n['id']}) {status}")
        elif node_on:
            print(f"  Mode: {c('green', 'NODE')}")
            print(f"  Node name: {self.config.get_node_name() or 'not set'}")
            print(f"  Master URL: {self.config.get_master_url() or 'not set'}")
            token = self.config.get_node_token()
            print(f"  Token: {'configured' if token else 'not registered yet'}")
        else:
            print(f"  Mode: {c('dim', 'STANDALONE')}")
        print()

    def _view_dashboard(self):
        print(c("bold", c("cyan", "\n  === Multi-Server Dashboard ===")))
        import json
        GB = 1024 * 1024 * 1024

        counter_data = self.db.get_all_node_data("counter")
        vcounter_data = self.db.get_all_node_data("vcounter")
        volume_data = self.db.get_all_node_data("volume")
        nodes = self.db.get_all_nodes()

        if not nodes:
            print("  No nodes registered yet.")
            return

        print(f"\n  {'Node':<25} {'Status':<10} {'Counter':<10} {'Bandwidth (GB)':<15}")
        print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*15}")

        total_counter = 0
        total_vcounter = 0

        node_status = {}
        for n in nodes:
            node_status[n["id"]] = {"name": n["name"], "online": False, "counter": 0, "vcounter_bytes": 0}
            if n["last_seen"]:
                try:
                    from datetime import datetime, timezone
                    seen = datetime.fromisoformat(n["last_seen"])
                    delta = datetime.now(timezone.utc) - seen
                    node_status[n["id"]]["online"] = delta.total_seconds() < 120
                except Exception:
                    pass

        for entry in counter_data:
            nid = entry["node_id"]
            if nid in node_status:
                try:
                    data = json.loads(entry["data_json"])
                    node_status[nid]["counter"] = data.get("report", {}).get("total", 0)
                except Exception:
                    pass

        for entry in vcounter_data:
            nid = entry["node_id"]
            if nid in node_status:
                try:
                    data = json.loads(entry["data_json"])
                    node_status[nid]["vcounter_bytes"] = data.get("report", {}).get("total_bytes", 0)
                except Exception:
                    pass

        for ns in node_status.values():
            status_str = c("green", "online") if ns["online"] else c("dim", "offline")
            ct = ns["counter"]
            vb = ns["vcounter_bytes"]
            total_counter += ct
            total_vcounter += vb
            print(f"  {ns['name']:<25} {status_str:<10} {ct:<10} {vb / GB:<15.2f}")

        print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*15}")
        print(f"  {'TOTAL':<25} {'':<10} {total_counter:<10} {total_vcounter / GB:<15.2f}")
        print()

    def _setup_ip_limit(self):
        print(c("bold", c("cyan", "\n  === IP Limit Configuration ===")))

        ip_enabled = self.config.get_ip_limit_enabled()
        current = "ON" if ip_enabled else "OFF"
        print(f"  IP Limit status: {c('green' if ip_enabled else 'dim', current)}")

        enable = self._ask("Enable IP limiting? (y/n)", "y" if ip_enabled else "n")
        self.config.set_ip_limit_enabled(enable.lower() == "y")

        if enable.lower() == "y":
            current_limit = self.config.get_ip_limit_all()
            limit = self._ask("Max IPs per user", str(current_limit))
            self.config.set_ip_limit_all(int(limit))

            ban_time = self.config.get_ban_time()
            ban = self._ask("Ban time (minutes)", str(ban_time))
            self.config.set_ban_time(int(ban))

            ssh_port = self.config.get_ssh_port()
            ssh = self._ask("SSH port", str(ssh_port))
            self.config.set_ssh_port(int(ssh))

            print(c("green", "\n  IP limit configuration saved."))

    def _run_flow_once(self, set_mode: bool):
        if not self._ensure_client():
            return
        flow_setter = FlowSetter(self.client)

        if set_mode:
            target = FlowSetter.FLOW_VALUE
            label = f"'{target}'"
            print(c("bold", c("cyan", "\n  === Set Flow (xtls-rprx-vision) ===")))
        else:
            target = FlowSetter.FLOW_NONE
            label = "none / empty"
            print(c("bold", c("cyan", "\n  === Clear Flow (unset) ===")))

        print(f"  Target: {label}")

        confirm = self._ask("Proceed? (y/n)", "y")
        if confirm.lower() != "y":
            return

        total, needed, updated, errors = flow_setter.run_once(target)
        print()
        print(c("cyan", "=" * 50))
        print(f"  Total users         : {total}")
        print(f"  Needed update       : {needed}")
        print(f"  Successfully updated: {len(updated)}")
        print(f"  Errors              : {len(errors)}")
        if updated:
            print(f"\n  Updated:")
            for n in updated:
                print(f"    - {n}")
        if errors:
            print(f"\n  Failed:")
            for n in errors:
                print(f"    - {n}")
        print(c("cyan", "=" * 50))

    def _configure_flow(self):
        print(c("bold", c("cyan", "\n  === Configure Flow ===")))
        print("  Choose the flow mode for the daemon:")
        print()
        print(f"  {c('cyan', '1')}.  Set flow = xtls-rprx-vision")
        print(f"  {c('cyan', '2')}.  Clear flow (unset / empty)")
        print()

        try:
            choice = int(input("  Choose: ").strip())
        except (ValueError, EOFError, KeyboardInterrupt):
            return

        if choice == 1:
            self.config.set_flow_value(FlowSetter.FLOW_VALUE)
            self.config.set_flow_enabled(True)
            print(c("green", f"\n  Flow set to '{FlowSetter.FLOW_VALUE}'. Flow updater enabled."))
        elif choice == 2:
            self.config.set_flow_value(FlowSetter.FLOW_NONE)
            self.config.set_flow_enabled(True)
            print(c("green", "\n  Flow cleared (unset). Flow updater enabled."))

    def _run_ip_limit_once(self):
        if not self._ensure_client():
            return
        ip_limiter = IPLimiter(self.client, self.config)

        print(c("bold", c("cyan", "\n  === Run IP Limiter (One-shot) ===")))
        print(f"  Max IPs per user: {self.config.get_ip_limit_all()}")

        confirm = self._ask("Proceed? (y/n)", "y")
        if confirm.lower() != "y":
            return

        total, new_users, _, _ = ip_limiter.run_once()
        print()
        print(c("cyan", "=" * 50))
        print(f"  Total users     : {total}")
        print(f"  New users added : {new_users}")
        print(c("cyan", "=" * 50))

    def _manage_ip_limits(self):
        if not self._ensure_client():
            return

        print(c("bold", c("cyan", "\n  === Manage IP Limits ===")))
        users = self.client.get_all_users()
        if not users:
            print("  No users found.")
            return

        options = [
            ("Set limit for all users", "all"),
            ("Set limit for specific user", "specific"),
            ("View all limits", "view"),
            ("Back", "back"),
        ]

        for i, (label, _) in enumerate(options, 1):
            print(f"  {c('cyan', str(i))}.  {label}")
        print()

        try:
            choice = int(input("  Choose: ").strip())
        except (ValueError, EOFError, KeyboardInterrupt):
            return

        if choice == 1:
            limit = self._ask("Max IPs per user", str(self.config.get_ip_limit_all()))
            self.config.set_ip_limit_all(int(limit))
            for user in users:
                self.db.set_ip_limit(user["username"], int(limit))
            print(c("green", f"\n  Limit set to {limit} for all {len(users)} users."))

        elif choice == 2:
            print("\n  Users:")
            for i, user in enumerate(users[:20], 1):
                current = self.db.get_ip_limit(user["username"]) or self.config.get_ip_limit_all()
                print(f"    {i}. {user['username']} (limit: {current})")
            print()
            uname = self._ask("Username")
            limit = self._ask("Max IPs")
            self.db.set_ip_limit(uname, int(limit))
            print(c("green", f"\n  Limit set to {limit} for {uname}."))

        elif choice == 3:
            print("\n  IP Limits:")
            print(f"  {'User':<30} {'Limit':<10}")
            print(f"  {'-'*30} {'-'*10}")
            all_limits = self.db.get_all_ip_limits()
            for email, limit in all_limits.items():
                print(f"  {email:<30} {limit:<10}")
            if not all_limits:
                print("  No limits configured.")
            print()

    def _toggle_features(self):
        print(c("bold", c("cyan", "\n  === Toggle Features ===")))

        flow = self.config.get_flow_enabled()
        ip = self.config.get_ip_limit_enabled()
        tg = self.config.get_telegram_enabled()
        ct = self.config.get_counter_enabled()
        vl = self.config.get_volume_limit_enabled()
        vc = self.config.get_vcounter_enabled()

        options = [
            (f"Flow updater:  {c('green' if flow else 'dim', 'ON' if flow else 'OFF')}", "flow"),
            (f"IP limiter:    {c('green' if ip else 'dim', 'ON' if ip else 'OFF')}", "ip"),
            (f"Telegram:      {c('green' if tg else 'dim', 'ON' if tg else 'OFF')}", "tg"),
            (f"User Counter:  {c('green' if ct else 'dim', 'ON' if ct else 'OFF')}", "ct"),
            (f"Traffic Limit: {c('green' if vl else 'dim', 'ON' if vl else 'OFF')}", "vl"),
            (f"Bandwidth:     {c('green' if vc else 'dim', 'ON' if vc else 'OFF')}", "vc"),
            ("Back", "back"),
        ]

        for i, (label, _) in enumerate(options, 1):
            print(f"  {c('cyan', str(i))}.  {label}")
        print()

        try:
            choice = int(input("  Choose: ").strip())
        except (ValueError, EOFError, KeyboardInterrupt):
            return

        if choice == 1:
            self.config.set_flow_enabled(not flow)
            print(c("green", f"\n  Flow updater {'enabled' if not flow else 'disabled'}."))
        elif choice == 2:
            self.config.set_ip_limit_enabled(not ip)
            print(c("green", f"\n  IP limiter {'enabled' if not ip else 'disabled'}."))
        elif choice == 3:
            self.config.set_telegram_enabled(not tg)
            if not tg:
                self.telegram.start()
            else:
                self.telegram.stop()
            print(c("green", f"\n  Telegram {'enabled' if not tg else 'disabled'}."))
        elif choice == 4:
            if not ct and vc:
                print(c("yellow", "\n  Cannot enable User Counter while Bandwidth Tracker is ON. Bandwidth Tracker disabled first."))
            self.config.set_counter_enabled(not ct)
            print(c("green", f"\n  User Counter {'enabled' if not ct else 'disabled'}."))
        elif choice == 5:
            self.config.set_volume_limit_enabled(not vl)
            if not vl:
                gb = self.config.get_volume_limit_gb()
                print(c("green", f"\n  Traffic Limit enabled ({gb} GB)."))
            else:
                print(c("green", "\n  Traffic Limit disabled."))
        elif choice == 6:
            if not vc and ct:
                print(c("yellow", "\n  Cannot enable Bandwidth Tracker while User Counter is ON. User Counter disabled first."))
            self.config.set_vcounter_enabled(not vc)
            print(c("green", f"\n  Bandwidth Tracker {'enabled' if not vc else 'disabled'}."))

    def _setup_volume_limit(self):
        print(c("bold", c("cyan", "\n  === Volume Limit Configuration ===")))

        vl_enabled = self.config.get_volume_limit_enabled()
        current = "ON" if vl_enabled else "OFF"
        print(f"  Status: {c('green' if vl_enabled else 'dim', current)}")

        enable = self._ask("Enable volume limit? (y/n)", "y" if vl_enabled else "n")
        self.config.set_volume_limit_enabled(enable.lower() == "y")

        if enable.lower() == "y":
            current_gb = self.config.get_volume_limit_gb()
            gb = self._ask("Max traffic per user (GB)", str(current_gb))
            self.config.set_volume_limit_gb(int(gb))
            print(c("green", f"\n  Volume limit set to {gb} GB."))
        else:
            print(c("green", "\n  Volume limit disabled."))

    def _manage_exempt_list(self):
        print(c("bold", c("cyan", "\n  === Manage Exempt Users ===")))
        exempt = self.db.get_all_exempt_users()
        if exempt:
            print(f"  {'Username':<30} {'Added At':<25}")
            print(f"  {'-'*30} {'-'*25}")
            for e in exempt:
                print(f"  {e['username']:<30} {e['added_at']:<25}")
        else:
            print("  No exempt users.")

        print()
        print(f"  {c('cyan', '1')}.  Add exempt user")
        print(f"  {c('cyan', '2')}.  Remove exempt user")
        print(f"  {c('cyan', '3')}.  Back")
        print()

        try:
            choice = int(input("  Choose: ").strip())
        except (ValueError, EOFError, KeyboardInterrupt):
            return

        if choice == 1:
            username = self._ask("Username to exempt")
            if username:
                from datetime import datetime, timezone
                self.db.add_exempt(username, datetime.now(timezone.utc).isoformat())
                print(c("green", f"\n  {username} added to exempt list."))
        elif choice == 2:
            username = self._ask("Username to remove from exempt")
            if username:
                self.db.remove_exempt(username)
                print(c("green", f"\n  {username} removed from exempt list."))

    def _start_web_dashboard(self):
        from modules.web_daemon import web_daemon_pid, spawn_web_daemon
        import socket

        pid = web_daemon_pid()
        if pid:
            print(c("yellow", f"\n  Web dashboard already running (PID {pid})."))
            return

        print(c("bold", c("cyan", "\n  === Start Web Dashboard ===")))
        port = self._ask("Port", str(self.config.get_web_port()))
        self.config.set_web_port(int(port))

        pid = spawn_web_daemon(self.config)
        if pid:
            hostname = socket.gethostname()
            print()
            print(c("green", f"  Web dashboard started (PID {pid})"))
            print()
            print(c("bold", "  Access URLs:"))
            print(c("dim",    f"    Local   : http://localhost:{port}"))
            print(c("dim",    f"    Network : http://{hostname}:{port}"))
            print()
        else:
            print(c("red", "\n  Failed to start web dashboard."))

    def _update_tool(self):
        import subprocess
        print(c("bold", c("cyan", "\n  === Update marzTool ===")))
        install_dir = "/opt/marztool"
        import os
        if not os.path.isdir(install_dir):
            print(c("yellow", f"  Install directory not found: {install_dir}"))
            return
        print(c("dim", f"  Running git pull in {install_dir}..."))
        result = subprocess.run(
            ["git", "pull"],
            cwd=install_dir,
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if "Already up to date" in output or "Already up-to-date" in output:
                print(c("green", "  Already up to date."))
            else:
                print(c("green", "  Updated successfully:"))
                for line in output.split("\n")[:10]:
                    print(c("dim", f"    {line}"))
        else:
            print(c("red", f"  Update failed:\n{result.stderr.strip()}"))

    def _setup_ssl(self):
        import subprocess as _sp
        import os
        print(c("bold", c("cyan", "\n  === SSL Certificate Setup ===")))
        print(c("dim", "  Auto-provisions SSL certificate for HTTPS using acme.sh"))
        print(c("dim", "  (falls back to certbot if acme.sh not installed)\n"))

        current_cert = self.config.get_ssl_cert()
        current_key = self.config.get_ssl_key()
        if current_cert and current_key:
            print(c("green", f"  Current cert: {current_cert}"))
            print(c("green", f"  Current key : {current_key}"))
            print()

        domain = self._ask("Domain name", "")
        email = self._ask("Email for Let's Encrypt", "")
        if not domain or not email:
            print(c("red", "  Domain and email are required."))
            return

        cert_dir = f"/opt/marztool/certs/{domain}"
        os.makedirs(cert_dir, exist_ok=True)

        acme = os.path.expanduser("~/.acme.sh/acme.sh")
        used = "acme.sh"

        if not os.path.exists(acme):
            print(c("dim", "  Installing acme.sh..."))
            r = _sp.run(
                ["curl", "-s", "https://get.acme.sh"],
                capture_output=True, text=True, timeout=30,
            )
            _sp.run(
                ["sh", "-s", "email=" + email],
                input=r.stdout, capture_output=True, text=True, timeout=60,
            )
            if not os.path.exists(acme):
                print(c("yellow", "  acme.sh install failed, trying certbot..."))
                used = "certbot"
                r = _sp.run(
                    ["certbot", "certonly", "--standalone", "-d", domain, "--non-interactive", "--agree-tos", "-m", email],
                    capture_output=True, text=True, timeout=120,
                )
                if r.returncode != 0:
                    print(c("red", f"  certbot failed:\n{r.stderr.strip()}"))
                    return
                cert_path = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
                key_path = f"/etc/letsencrypt/live/{domain}/privkey.pem"
            else:
                print(c("dim", "  Issuing certificate..."))
                r = _sp.run(
                    [acme, "--issue", "--standalone", "-d", domain, "--accountemail", email],
                    capture_output=True, text=True, timeout=120,
                )
                if r.returncode != 0:
                    print(c("red", f"  acme.sh failed:\n{r.stderr.strip()}"))
                    return
                cert_path = os.path.expanduser(f"~/.acme.sh/{domain}_ecc/fullchain.cer")
                key_path = os.path.expanduser(f"~/.acme.sh/{domain}_ecc/{domain}.key")
        else:
            print(c("dim", "  Issuing certificate with acme.sh..."))
            r = _sp.run(
                [acme, "--issue", "--standalone", "-d", domain, "--accountemail", email],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0:
                print(c("red", f"  acme.sh failed:\n{r.stderr.strip()}"))
                return
            cert_path = os.path.expanduser(f"~/.acme.sh/{domain}_ecc/fullchain.cer")
            key_path = os.path.expanduser(f"~/.acme.sh/{domain}_ecc/{domain}.key")

        print(c("dim", f"  Installing certificate to {cert_dir}..."))
        _sp.run([acme if used == "acme.sh" else "certbot", "install-cert" if used == "acme.sh" else "cert",
                  "-d", domain, "--key-file", f"{cert_dir}/privkey.pem",
                  "--fullchain-file", f"{cert_dir}/fullchain.pem",
                  "--reloadcmd", "echo reloaded"],
                 capture_output=True, text=True, timeout=30) if used == "acme.sh" else None

        import shutil
        if used == "certbot" or not os.path.exists(f"{cert_dir}/fullchain.pem"):
            for src, name in [(cert_path, "fullchain.pem"), (key_path, "privkey.pem")]:
                if os.path.exists(src):
                    shutil.copy2(src, f"{cert_dir}/{name}")

        if os.path.exists(f"{cert_dir}/fullchain.pem") and os.path.exists(f"{cert_dir}/privkey.pem"):
            self.config.set_ssl_cert(f"{cert_dir}/fullchain.pem")
            self.config.set_ssl_key(f"{cert_dir}/privkey.pem")
            print(c("green", f"\n  SSL certificate installed successfully!"))
            print(c("dim", f"  Cert: {cert_dir}/fullchain.pem"))
            print(c("dim", f"  Key : {cert_dir}/privkey.pem"))
            print(c("dim", "  Restart web dashboard to apply."))
        else:
            print(c("red", "\n  Certificate files not found after install."))

    def _view_vcounter(self):
        print(c("bold", c("cyan", "\n  === Bandwidth Tracker Report ===")))
        from modules.vcounter import VCounter
        vc = VCounter(None, self.db)
        try:
            report = vc.get_report(viewer="tui")
            if not report["admins"]:
                print("  No volume data yet.")
                return
            GB = 1024 * 1024 * 1024
            print()
            print(f"  {'Admin':<30} {'Volume (GB)':<15}")
            print(f"  {'-'*30} {'-'*15}")
            for a in report["admins"]:
                gb = a['total_volume_bytes'] / GB
                print(f"  {a['admin_username']:<30} {gb:<15.2f}")
            print(f"  {'-'*30} {'-'*15}")
            print(f"  {'TOTAL':<30} {report['total_bytes'] / GB:<15.2f}")
        except Exception as e:
            print(c("red", f"  Error: {e}"))

    def _settle(self):
        print(c("bold", c("cyan", "\n  === Settlements ===")))
        print("  Reset your personal view without affecting the grand total.")
        print()
        print(f"  {c('cyan', '1')}.  Settle User Counter (reset your config count)")
        print(f"  {c('cyan', '2')}.  Settle Bandwidth Tracker (reset your bandwidth total)")
        print(f"  {c('cyan', '3')}.  View Counter Settlements")
        print(f"  {c('cyan', '4')}.  View Bandwidth Settlements")
        print(f"  {c('cyan', '5')}.  Back")
        print()

        try:
            choice = int(input("  Choose: ").strip())
        except (ValueError, EOFError, KeyboardInterrupt):
            return

        if choice == 1:
            username = self.config.get_username()
            if not username:
                print(c("red", "\n  Admin username not configured."))
                return
            from modules.counter import Counter
            counter = Counter(None, self.db)
            settled = counter.settle(username, "tui")
            if settled <= 0:
                print(c("yellow", "\n  Nothing to settle."))
            else:
                print(c("green", f"\n  Counter settled. Reset {settled} configs from your view."))
        elif choice == 2:
            username = self.config.get_username()
            if not username:
                print(c("red", "\n  Admin username not configured."))
                return
            from modules.vcounter import VCounter
            vc = VCounter(None, self.db)
            settled = vc.settle(username, "tui")
            GB = 1024 * 1024 * 1024
            if settled <= 0:
                print(c("yellow", "\n  Nothing to settle."))
            else:
                print(c("green", f"\n  Bandwidth settled. Reset {settled / GB:.2f} GB from your view."))
        elif choice == 3:
            settlements = self.db.get_counter_settlements()
            if not settlements:
                print(c("yellow", "\n  No settlements."))
                return
            print()
            for s in settlements[:10]:
                print(f"  {s['admin_username']} settled by {s['settled_by']}: {s['amount_count']} configs")
                print(f"    {s['settled_at'][:16]}")
        elif choice == 4:
            settlements = self.db.get_vcounter_settlements()
            if not settlements:
                print(c("yellow", "\n  No settlements."))
                return
            GB = 1024 * 1024 * 1024
            print()
            for s in settlements[:10]:
                print(f"  {s['admin_username']} settled by {s['settled_by']}: {s['amount_bytes'] / GB:.2f} GB")
                print(f"    {s['settled_at'][:16]}")

    def _view_counter(self):
        if not self._ensure_client():
            return
        from modules.counter import Counter
        counter = Counter(self.client, self.db)
        print(c("bold", c("cyan", "\n  === Counter Report ===")))
        print("  Syncing with panel...")
        try:
            counter.sync()
            report = counter.get_report(viewer="tui")
            if not report["admins"]:
                print("  No counts yet.")
                return
            print()
            print(f"  {'Admin':<30} {'Count':<10}")
            print(f"  {'-'*30} {'-'*10}")
            for a in report["admins"]:
                print(f"  {a['admin_username']:<30} {a['total_count']:<10}")
            print(f"  {'-'*30} {'-'*10}")
            print(f"  {'TOTAL':<30} {report['total']:<10}")
        except Exception as e:
            print(c("red", f"  Error: {e}"))

    def _reset_counter(self):
        print(c("bold", c("cyan", "\n  === Reset Counter ===")))
        confirm = self._ask("Reset ALL counters? (y/n)", "n")
        if confirm.lower() != "y":
            return
        self.db.reset_all_counters()
        print(c("green", "\n  All counters reset."))

    def _start_daemon(self):
        pid = daemon_pid()
        if pid:
            print(c("yellow", f"\n  Daemon already running (PID {pid})."))
            print("  Stop it first before launching a new one.")
            return

        if not self._ensure_client():
            return

        flow = self.config.get_flow_enabled()
        ip = self.config.get_ip_limit_enabled()
        ct = self.config.get_counter_enabled()
        vl = self.config.get_volume_limit_enabled()
        vc = self.config.get_vcounter_enabled()

        if not flow and not ip and not ct and not vl and not vc:
            print(c("yellow", "\n  No features enabled. Enable flow, IP limit, counter, volume limit, or vcounter first."))
            return

        print(c("bold", c("cyan", "\n  === Start Daemon ===")))
        interval = self._ask("Check interval (seconds)", str(self.config.get_daemon_interval()))
        self.config.set_daemon_interval(int(interval))

        flow_val = self.config.get_flow_value()
        flow_label = f"ON ({flow_val})" if flow else "OFF"
        print(f"  Features: Flow={flow_label}  IP Limit={'ON' if ip else 'OFF'}  Counter={'ON' if ct else 'OFF'}  Traffic={'ON' if vl else 'OFF'}  Bandwidth={'ON' if vc else 'OFF'}")
        print(f"  Interval: {interval}s")

        try:
            if self.telegram.app:
                self.telegram.stop()
            pid = spawn_daemon(self.config)
            print(c("green", f"\n  Daemon started (PID {pid})."))
        except Exception as e:
            print(c("red", f"\n  Failed to start daemon: {e}"))

    def _view_settings(self):
        print(c("bold", c("cyan", "\n  === Current Settings ===")))
        flow_val = self.config.get_flow_value()
        settings = {
            "Server URL": self.config.get_server_url() or "not set",
            "Username": self.config.get_username() or "not set",
            "Password": "*" * 8 if self.config.get_password() else "not set",
            "Flow mode": f"'{flow_val}'" if flow_val else "unset (empty)",
            "Flow enabled": str(self.config.get_flow_enabled()),
            "IP limit (all)": str(self.config.get_ip_limit_all()),
            "IP limit enabled": str(self.config.get_ip_limit_enabled()),
            "Counter enabled": str(self.config.get_counter_enabled()),
            "Daemon interval": f"{self.config.get_daemon_interval()}s",
            "Ban time": f"{self.config.get_ban_time()} min",
            "SSH port": str(self.config.get_ssh_port()),
            "Telegram enabled": str(self.config.get_telegram_enabled()),
            "Telegram token": "*" * 8 if self.config.get_telegram_token() else "not set",
            "Telegram admin": self.config.get_telegram_admin_id() or "not set",
            "Traffic limit enabled": str(self.config.get_volume_limit_enabled()),
            "Traffic limit (GB)": str(self.config.get_volume_limit_gb()),
            "Bandwidth tracker enabled": str(self.config.get_vcounter_enabled()),
        }
        for key, val in settings.items():
            print(f"  {c('dim', key + ':'):<35} {val}")
        print()

    def run(self):
        while True:
            self._banner()
            pid = daemon_pid()

            main_options = [
                ("Panel connection (setup wizard)", "setup"),
                ("Toggle features on/off", "toggle"),
                ("VLESS Flow", "submenu_flow"),
                ("IP Limiter", "submenu_ip"),
                ("User Counter", "submenu_counter"),
                ("Bandwidth Tracker", "submenu_bw"),
                ("Traffic Limiter", "submenu_traffic"),
                ("Settlements", "settle"),
                ("Services (daemon / web)", "submenu_services"),
                ("Settings & Telegram", "submenu_settings"),
                ("Update (git pull)", "update"),
                ("Exit", "exit"),
            ]

            choice = self._menu(main_options)
            if choice == -1:
                continue

            action = main_options[choice][1]

            if action == "exit":
                print("\n  Goodbye.\n")
                self.db.close()
                sys.exit(0)

            elif action == "setup":
                self._setup_wizard()
                input("\n  [Enter to continue] ")

            elif action == "toggle":
                self._toggle_features()
                input("\n  [Enter to continue] ")

            elif action == "submenu_flow":
                self._submenu_flow()

            elif action == "submenu_ip":
                self._submenu_ip()

            elif action == "submenu_counter":
                self._submenu_counter()

            elif action == "submenu_bw":
                self._submenu_bw()

            elif action == "submenu_traffic":
                self._submenu_traffic()

            elif action == "settle":
                self._settle()
                input("\n  [Enter to continue] ")

            elif action == "submenu_services":
                self._submenu_services()

            elif action == "submenu_settings":
                self._submenu_settings()

            elif action == "update":
                self._update_tool()
                input("\n  [Enter to continue] ")

    def _submenu_flow(self):
        options = [
            ("Configure flow mode (set / clear)", "flow_config"),
            ("Apply flow now (set xtls-rprx-vision)", "flow_set"),
            ("Apply flow now (clear / unset)", "flow_clear"),
            ("Back", "back"),
        ]
        choice = self._menu(options)
        if choice == -1:
            return
        action = options[choice][1]
        if action == "flow_config":
            self._configure_flow()
            input("\n  [Enter to continue] ")
        elif action == "flow_set":
            self._run_flow_once(set_mode=True)
            input("\n  [Enter to continue] ")
        elif action == "flow_clear":
            self._run_flow_once(set_mode=False)
            input("\n  [Enter to continue] ")

    def _submenu_ip(self):
        options = [
            ("IP limit settings", "ip_config"),
            ("Manage per-user IP limits", "ip_manage"),
            ("Run IP limiter now", "ip_once"),
            ("Back", "back"),
        ]
        choice = self._menu(options)
        if choice == -1:
            return
        action = options[choice][1]
        if action == "ip_config":
            self._setup_ip_limit()
            input("\n  [Enter to continue] ")
        elif action == "ip_manage":
            self._manage_ip_limits()
            input("\n  [Enter to continue] ")
        elif action == "ip_once":
            self._run_ip_limit_once()
            input("\n  [Enter to continue] ")

    def _submenu_counter(self):
        options = [
            ("View counter report", "counter_view"),
            ("Reset counter", "counter_reset"),
            ("Back", "back"),
        ]
        choice = self._menu(options)
        if choice == -1:
            return
        action = options[choice][1]
        if action == "counter_view":
            self._view_counter()
            input("\n  [Enter to continue] ")
        elif action == "counter_reset":
            self._reset_counter()
            input("\n  [Enter to continue] ")

    def _submenu_bw(self):
        options = [
            ("View bandwidth report", "vcounter_view"),
            ("Back", "back"),
        ]
        choice = self._menu(options)
        if choice == -1:
            return
        action = options[choice][1]
        if action == "vcounter_view":
            self._view_vcounter()
            input("\n  [Enter to continue] ")

    def _submenu_traffic(self):
        print(c("dim", "\n  For unlimited configs with fair usage — monitors consumed traffic"))
        print(c("dim", "  in the background and auto-disables users who exceed the threshold.\n"))
        options = [
            ("Traffic limit settings", "vl_config"),
            ("Manage exempt users", "vl_exempt_list"),
            ("Back", "back"),
        ]
        choice = self._menu(options)
        if choice == -1:
            return
        action = options[choice][1]
        if action == "vl_config":
            self._setup_volume_limit()
            input("\n  [Enter to continue] ")
        elif action == "vl_exempt_list":
            self._manage_exempt_list()
            input("\n  [Enter to continue] ")

    def _submenu_services(self):
        from modules.web_daemon import web_daemon_pid, web_daemon_port
        pid = daemon_pid()
        web_pid = web_daemon_pid()

        options = []
        if pid:
            options.append(("Stop daemon", "daemon_stop"))
            options.append(("View daemon logs", "daemon_logs"))
        else:
            options.append(("Start daemon", "daemon_start"))

        options.append(("---", "---"))

        if web_pid:
            port = web_daemon_port()
            options.append((f"Stop web dashboard (port {port})", "web_stop"))
            options.append(("View web dashboard logs", "web_logs"))
        else:
            options.append(("Start web dashboard", "web_start"))

        options.append(("Back", "back"))

        choice = self._menu(options)
        if choice == -1:
            return
        action = options[choice][1]
        if action == "daemon_start":
            self._start_daemon()
            input("\n  [Enter to continue] ")
        elif action == "daemon_stop":
            stop_daemon()
            if self.config.get_telegram_enabled():
                self.telegram.start()
            input("\n  [Enter to continue] ")
        elif action == "daemon_logs":
            view_logs()
            input("\n  [Enter to continue] ")
        elif action == "web_start":
            self._start_web_dashboard()
            input("\n  [Enter to continue] ")
        elif action == "web_stop":
            from modules.web_daemon import stop_web_daemon
            stop_web_daemon()
            print(c("green", "\n  Web dashboard stopped."))
            input("\n  [Enter to continue] ")
        elif action == "web_logs":
            from modules.web_daemon import web_daemon_log
            logs = web_daemon_log(50)
            print(c("bold", c("cyan", "\n  === Web Dashboard Logs ===")))
            print(c("dim", logs or "No logs yet."))
            input("\n  [Enter to continue] ")

    def _submenu_settings(self):
        options = [
            ("View settings", "settings"),
            ("Telegram setup", "telegram"),
            ("Test Telegram connection", "test_telegram"),
            ("SSL certificate setup", "ssl"),
            ("Master / Node configuration", "master_node"),
        ]
        if self.config.get_master_enabled():
            options.append(("View multi-server dashboard", "dashboard"))
        options.append(("Back", "back"))

        choice = self._menu(options)
        if choice == -1:
            return
        action = options[choice][1]
        if action == "settings":
            self._view_settings()
            input("\n  [Enter to continue] ")
        elif action == "telegram":
            self._setup_telegram()
            input("\n  [Enter to continue] ")
        elif action == "test_telegram":
            self._test_telegram()
            input("\n  [Enter to continue] ")
        elif action == "master_node":
            self._setup_master_node()
            input("\n  [Enter to continue] ")
        elif action == "ssl":
            self._setup_ssl()
            input("\n  [Enter to continue] ")
        elif action == "dashboard":
            self._view_dashboard()
            input("\n  [Enter to continue] ")
