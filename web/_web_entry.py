import json
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.web_daemon import WEB_PID_FILE, WEB_CONFIG_FILE, TEMP_DIR


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
    dash.start()

    log.info("Web dashboard daemon running on port %d (PID %d)", port, os.getpid())

    import time
    while True:
        time.sleep(1)


if __name__ == "__main__":
    _main()
