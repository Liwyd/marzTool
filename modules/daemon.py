import json
import logging
import os
import signal
import sys
import tempfile
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _get_temp_dir() -> Path:
    if sys.platform == "win32":
        return Path(tempfile.gettempdir()) / "marztool"
    return Path("/tmp/marztool")


TEMP_DIR = _get_temp_dir()
TEMP_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = TEMP_DIR / "daemon.pid"
LOG_FILE = TEMP_DIR / "daemon.log"
CONFIG_FILE = TEMP_DIR / "daemon_config.json"
LOG_MAX = 900_000
LOG_KEEP = 1


def _make_logger(name: str, to_file: bool = False) -> logging.Logger:
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        if to_file:
            h = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX, backupCount=LOG_KEEP)
        else:
            h = logging.StreamHandler()
        h.setFormatter(fmt)
        logger.addHandler(h)
    return logger


def _is_process_running(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def daemon_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        if _is_process_running(pid):
            return pid
        PID_FILE.unlink(missing_ok=True)
        return None
    except (ValueError, OSError):
        PID_FILE.unlink(missing_ok=True)
        return None


def stop_daemon():
    pid = daemon_pid()
    if pid is None:
        print("\n  No running daemon found.\n")
        return
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10)
        else:
            os.kill(pid, signal.SIGTERM)
        time.sleep(0.8)
        PID_FILE.unlink(missing_ok=True)
        CONFIG_FILE.unlink(missing_ok=True)
        print(f"\n  Daemon (PID {pid}) stopped.\n")
    except (ProcessLookupError, Exception):
        PID_FILE.unlink(missing_ok=True)
        CONFIG_FILE.unlink(missing_ok=True)
        print("\n  Daemon was already dead. PID file removed.\n")


def view_logs(lines: int = 40):
    if not LOG_FILE.exists():
        print("\n  No log file found yet.\n")
        return
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        recent = all_lines[-lines:]
        print()
        print("-" * 65)
        print(f"  Last {lines} lines of {LOG_FILE}")
        print("-" * 65)
        for line in recent:
            print("  " + line.rstrip())
        if not recent:
            print("  (empty)")
        print("-" * 65)
        print(f"  Press 'q' + Enter to stop watching, or just Enter to refresh")
        print("-" * 65)
        print()

        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            last_pos = len(all_lines)

        while True:
            try:
                user_input = input("  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if user_input == "q":
                break

            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            new_lines = all_lines[last_pos:]
            if new_lines:
                for line in new_lines:
                    print("  " + line.rstrip())
            else:
                print("  (no new logs)")
            last_pos = len(all_lines)

    except Exception as e:
        print(f"\n  Error reading logs: {e}\n")


def _daemon_worker(config_dict: dict):
    log = _make_logger("daemon", to_file=True)

    def _exit(sig, _):
        log.info("Signal %s -- shutting down.", sig)
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, _exit)
    signal.signal(signal.SIGTERM, _exit)

    PID_FILE.write_text(str(os.getpid()))

    from modules.api_client import MarzbanClient
    from modules.flow_setter import FlowSetter
    from modules.ip_limiter import IPLimiter
    from modules.counter import Counter
    from modules.database import Database
    from modules.config import Config

    db = Database(config_dict["db_path"])
    config = Config(db)

    server_url = config_dict["server_url"]
    username = config_dict["username"]
    password = config_dict["password"]
    interval = config_dict["interval"]
    flow_enabled = config_dict["flow_enabled"]
    ip_limit_enabled = config_dict["ip_limit_enabled"]
    counter_enabled = config_dict.get("counter_enabled", False)
    telegram_enabled = config_dict.get("telegram_enabled", False)
    volume_limit_enabled = config_dict.get("volume_limit_enabled", False)
    vcounter_enabled = config_dict.get("vcounter_enabled", False)

    log.info(
        "Daemon started. PID=%d  server=%s  flow=%s  ip_limit=%s  counter=%s  telegram=%s  volume_limit=%s  vcounter=%s  interval=%ds",
        os.getpid(), server_url, flow_enabled, ip_limit_enabled, counter_enabled, telegram_enabled, volume_limit_enabled, vcounter_enabled, interval,
    )

    client = MarzbanClient(server_url, log)
    try:
        client.login(username, password)
        log.info("Login OK -> %s", client.base_url)
    except Exception as e:
        log.error("Initial login failed: %s", e)
        PID_FILE.unlink(missing_ok=True)
        sys.exit(1)

    flow_setter = FlowSetter(client, log)
    ip_limiter = IPLimiter(client, config, log)
    counter = Counter(client, db, log)

    tg_bot = None
    if telegram_enabled:
        try:
            from modules.telegram_bot import TelegramBot
            tg_bot = TelegramBot(config, log)
            if tg_bot.start():
                log.info("Telegram bot started (polling)")
            else:
                log.warning("Telegram bot failed to start")
                tg_bot = None
        except Exception as e:
            log.error("Telegram bot init error: %s", e)
            tg_bot = None

    volume_limiter = None
    if volume_limit_enabled:
        try:
            from modules.volume_limiter import VolumeLimiter
            volume_limiter = VolumeLimiter(client, config, db, log)
            log.info("Volume limiter enabled (limit: %d GB)", config.get_volume_limit_gb())
        except Exception as e:
            log.error("Volume limiter init error: %s", e)

    vcounter = None
    if vcounter_enabled:
        try:
            from modules.vcounter import VCounter
            vcounter = VCounter(client, db, log)
            log.info("VCounter enabled")
        except Exception as e:
            log.error("VCounter init error: %s", e)

    cycle = 0
    while True:
        cycle += 1
        log.info("--- Cycle #%d ---", cycle)

        users = None
        try:
            users = client.get_all_users()
            log.info("Fetched %d users.", len(users))
        except Exception as e:
            log.error("Fetch users failed: %s", e)
            try:
                client.login(username, password)
                log.info("Re-login OK.")
                users = client.get_all_users()
                log.info("Fetched %d users (after re-login).", len(users))
            except Exception as re:
                log.error("Re-login failed: %s. Skipping cycle.", re)
                log.info("Sleeping %ds.", interval)
                time.sleep(interval)
                continue

        if ip_limit_enabled:
            try:
                total, new_users, updated, errors = ip_limiter.process_cycle(users=users)
                if new_users > 0:
                    log.info("IP limit: %d new users registered.", new_users)
                else:
                    log.info("IP limit: All %d users tracked.", total)
            except Exception as e:
                log.error("IP limit cycle error: %s", e)

        if counter_enabled:
            try:
                counter.sync(users)
                counter.detect_resets(users)
                notifs = db.get_pending_reset_notifications()
                tg_token = config_dict.get("telegram_token")
                tg_admin = config_dict.get("telegram_admin_id")
                if notifs and tg_token and tg_admin:
                    import requests as _req
                    for n in notifs:
                        msg = (
                            f"User Reset Detected!\n\n"
                            f"Admin: {n['admin_username']}\n"
                            f"User: {n['username']}\n"
                            f"Previous traffic: {n['prev_traffic_bytes'] / (1024*1024):.1f} MB\n"
                            f"Reset at: {n['reset_at']}"
                        )
                        try:
                            _req.get(
                                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                                json={"chat_id": int(tg_admin), "text": msg},
                                timeout=10,
                            )
                        except Exception as te:
                            log.error("Telegram notify error: %s", te)
                        db.clear_reset_notification(n["id"])
            except Exception as e:
                log.error("Counter cycle error: %s", e)

        if vcounter is not None:
            try:
                vcounter.sync(users)
                log.info("VCounter: sync complete.")
            except Exception as e:
                log.error("VCounter cycle error: %s", e)

        if flow_enabled:
            try:
                target_flow = config.get_flow_value()
                total, needed, updated, errors = flow_setter.process_cycle(target_flow, users=users)
                if needed == 0:
                    log.info("Flow: All %d users OK.", total)
                else:
                    log.info(
                        "Flow: %d/%d needed | updated=%d | errors=%d",
                        needed, total, len(updated), len(errors),
                    )
            except Exception as e:
                log.error("Flow cycle error: %s", e)

        if volume_limiter is not None:
            try:
                disabled = volume_limiter.process_cycle(users=users)
                if disabled:
                    log.info("Volume limit: %d users disabled.", len(disabled))
                    tg_token = config_dict.get("telegram_token")
                    tg_admin = config_dict.get("telegram_admin_id")
                    if tg_token and tg_admin:
                        import requests as _req
                        for d in disabled:
                            msg = (
                                f"Volume Limit Exceeded!\n\n"
                                f"User: {d['username']}\n"
                                f"Admin: {d['admin_username'] or '?'}\n"
                                f"Used: {d['used_gb']} GB\n"
                                f"Limit: {d['limit_gb']} GB\n"
                                f"Status: DISABLED"
                            )
                            kb = {
                                "inline_keyboard": [[
                                    {"text": "Exempt this user", "callback_data": f"vl_exempt:{d['username']}:{d['notif_id']}"}
                                ]]
                            }
                            try:
                                r = _req.post(
                                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                                    json={
                                        "chat_id": int(tg_admin),
                                        "text": msg,
                                        "reply_markup": kb,
                                    },
                                    timeout=10,
                                )
                                resp = r.json()
                                if resp.get("ok"):
                                    chat_id = resp["result"]["chat"]["id"]
                                    message_id = resp["result"]["message_id"]
                                    db.update_notification_message(d["notif_id"], chat_id, message_id)
                            except Exception as te:
                                log.error("Telegram volume notify error: %s", te)
                else:
                    log.info("Volume limit: all users within limit.")
            except Exception as e:
                log.error("Volume limit cycle error: %s", e)

        log.info("Sleeping %ds.", interval)
        time.sleep(interval)


def spawn_daemon(config):
    import subprocess

    config_dict = {
        "server_url": config.get_server_url(),
        "username": config.get_username(),
        "password": config.get_password(),
        "interval": config.get_daemon_interval(),
        "flow_enabled": config.get_flow_enabled(),
        "ip_limit_enabled": config.get_ip_limit_enabled(),
        "counter_enabled": config.get_counter_enabled(),
        "telegram_enabled": config.get_telegram_enabled(),
        "volume_limit_enabled": config.get_volume_limit_enabled(),
        "vcounter_enabled": config.get_vcounter_enabled(),
        "telegram_token": config.get_telegram_token(),
        "telegram_admin_id": config.get_telegram_admin_id(),
        "db_path": str(config.db.db_path),
    }

    CONFIG_FILE.write_text(json.dumps(config_dict), encoding="utf-8")

    script = Path(__file__).parent / "_daemon_entry.py"
    cmd = [sys.executable, str(script)]
    cwd = str(Path(__file__).parent.parent)

    creationflags = 0
    if sys.platform == "win32":
        creationflags = 0x00000008

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    time.sleep(2)
    return proc.pid


if __name__ == "__main__":
    if "--_daemon" in sys.argv:
        if CONFIG_FILE.exists():
            config_dict = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            _daemon_worker(config_dict)
        else:
            print("No config file found.")
            sys.exit(1)
