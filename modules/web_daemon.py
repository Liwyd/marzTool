import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path


def _get_temp_dir() -> Path:
    if sys.platform == "win32":
        return Path(tempfile.gettempdir()) / "marztool"
    return Path("/tmp/marztool")


TEMP_DIR = _get_temp_dir()
TEMP_DIR.mkdir(parents=True, exist_ok=True)
WEB_PID_FILE = TEMP_DIR / "web_dashboard.pid"
WEB_CONFIG_FILE = TEMP_DIR / "web_config.json"
WEB_LOG_FILE = TEMP_DIR / "web_daemon.log"


def web_daemon_pid() -> int | None:
    if not WEB_PID_FILE.exists():
        return None
    try:
        pid = int(WEB_PID_FILE.read_text().strip())
        if _is_running(pid):
            return pid
        WEB_PID_FILE.unlink(missing_ok=True)
        return None
    except (ValueError, OSError):
        WEB_PID_FILE.unlink(missing_ok=True)
        return None


def web_daemon_port() -> int | None:
    if not WEB_CONFIG_FILE.exists():
        return None
    try:
        cfg = json.loads(WEB_CONFIG_FILE.read_text(encoding="utf-8"))
        return cfg.get("port")
    except Exception:
        return None


def _is_running(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def spawn_web_daemon(config) -> int:
    port = config.get_web_port()
    ssl_cert = config.get_ssl_cert() or ""
    ssl_key = config.get_ssl_key() or ""
    db_path = str(config.db.db_path)

    if ssl_cert and not os.path.exists(ssl_cert):
        ssl_cert = ""
    if ssl_key and not os.path.exists(ssl_key):
        ssl_key = ""

    cfg = {"port": port, "ssl_cert": ssl_cert, "ssl_key": ssl_key, "db_path": db_path}
    WEB_CONFIG_FILE.write_text(json.dumps(cfg), encoding="utf-8")

    script = Path(__file__).parent.parent / "web" / "_web_entry.py"
    cmd = [sys.executable, str(script)]
    cwd = str(Path(__file__).parent.parent)

    creationflags = 0
    if sys.platform == "win32":
        creationflags = 0x00000008

    log_file = TEMP_DIR / "web_daemon.log"

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=open(log_file, "w"),
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    import time
    time.sleep(1.5)
    return proc.pid


def stop_web_daemon():
    pid = web_daemon_pid()
    if pid is None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10)
        else:
            os.kill(pid, signal.SIGTERM)
        import time
        time.sleep(0.5)
    except Exception:
        pass
    WEB_PID_FILE.unlink(missing_ok=True)
    WEB_CONFIG_FILE.unlink(missing_ok=True)


def web_daemon_log(lines: int = 30) -> str:
    if not WEB_LOG_FILE.exists():
        return ""
    try:
        with open(WEB_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except Exception:
        return ""
