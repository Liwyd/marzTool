import json
import os
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

WEB_LOG = Path("/tmp/marztool/web_daemon.log")


def _log(msg):
    WEB_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(WEB_LOG, "a") as f:
        f.write(f"  {msg}\n")


def _ensure_flask():
    try:
        import flask  # noqa: F401
        return True
    except ImportError:
        pass

    py = sys.executable
    _log("Flask not found. Attempting install...")

    methods = [
        ("pip --break-system-packages", [py, "-m", "pip", "install", "--break-system-packages", "flask"]),
        ("pip --root-user-action=ignore", [py, "-m", "pip", "install", "--root-user-action=ignore", "flask"]),
        ("apt python3-flask", ["apt-get", "install", "-y", "python3-flask"]),
    ]

    for name, cmd in methods:
        _log(f"Trying {name}...")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                _log(f"  OK")
                try:
                    import flask  # noqa: F401
                    _log("Flask imported successfully.")
                    return True
                except ImportError:
                    _log("  Installed but still can't import.")
            else:
                _log(f"  Failed (rc={r.returncode}): {r.stderr[:300]}")
        except Exception as e:
            _log(f"  Error: {e}")

    _log("All install methods failed.")
    return False


if not _ensure_flask():
    _log("Flask is NOT available. Web dashboard cannot start.")
    sys.exit(1)

from modules.web_daemon import WEB_PID_FILE, WEB_CONFIG_FILE, TEMP_DIR  # noqa: E402


def _main():
    if not WEB_CONFIG_FILE.exists():
        print("No web config found.")
        sys.exit(1)

    cfg = json.loads(WEB_CONFIG_FILE.read_text(encoding="utf-8"))
    port = cfg.get("port", 8080)
    ssl_cert = cfg.get("ssl_cert", "")
    ssl_key = cfg.get("ssl_key", "")
    db_path = cfg.get("db_path")

    PID_FILE = WEB_PID_FILE
    PID_FILE.write_text(str(os.getpid()))

    def _exit(sig, _):
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, _exit)
    signal.signal(signal.SIGTERM, _exit)

    import logging
    log = logging.getLogger("web_daemon")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%Y-%m-%d %H:%M:%S")
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    log.addHandler(handler)

    from modules.database import Database
    from modules.config import Config
    from web.app import WebDashboard

    db = Database(db_path)
    config = Config(db)

    if ssl_cert:
        config.set_ssl_cert(ssl_cert)
    if ssl_key:
        config.set_ssl_key(ssl_key)
    config.set_web_port(port)

    dash = WebDashboard(db, config, port=port, logger=log)
    if not dash.start():
        log.error("Flask not installed. Run: sudo apt install python3-flask")
        PID_FILE.unlink(missing_ok=True)
        sys.exit(1)

    log.info("Web dashboard daemon running on port %d (PID %d)", port, os.getpid())

    import time
    while True:
        time.sleep(1)


if __name__ == "__main__":
    _main()
