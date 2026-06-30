#!/usr/bin/env python3
"""
MarzTool - Marzban Management Suite

A unified tool for managing Marzban panels with features:
  - VLESS Flow management (set/clear xtls-rprx-vision)
  - IP limiting per user with automatic banning
  - Unified daemon for background operation
  - Telegram bot integration
  - Multi-server master/node management
  - Web dashboard

Usage:
  python marzTool.py          # interactive TUI
  python marzTool.py --auto   # start daemon with current settings
  python marzTool.py --master # start master API server
  python marzTool.py --web    # start web dashboard on port 8080
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.tui import TUI
from modules.daemon import spawn_daemon, stop_daemon, view_logs
from modules.database import Database
from modules.config import Config


def main():
    args = sys.argv[1:]

    if "--auto" in args:
        db = Database()
        config = Config(db)
        if not config.has_credentials():
            print("  Credentials not configured. Run without --auto first.")
            sys.exit(1)
        pid = spawn_daemon(config)
        print(f"  Daemon started (PID {pid})")
        db.close()
        return

    if "--stop" in args:
        stop_daemon()
        return

    if "--logs" in args:
        view_logs()
        return

    if "--master" in args:
        db = Database()
        config = Config(db)
        if not config.get_master_enabled():
            print("  Master mode not enabled. Configure in TUI first.")
            sys.exit(1)
        from modules.master_api import MasterAPI
        import logging
        log = logging.getLogger("master_standalone")
        log.setLevel(logging.INFO)
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%Y-%m-%d %H:%M:%S"))
        log.addHandler(h)
        port = config.get_master_port()
        api = MasterAPI(db, port=port, logger=log)
        api.start()
        print(f"  Master API running on port {port}")
        print("  Press Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n  Stopping...")
            api.stop()
            db.close()
        return

    if "--web" in args:
        import logging
        log = logging.getLogger("web_standalone")
        log.setLevel(logging.INFO)
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%Y-%m-%d %H:%M:%S"))
        log.addHandler(h)

        port = 8080
        if "--port" in args:
            idx = args.index("--port")
            if idx + 1 < len(args):
                port = int(args[idx + 1])

        db = Database()
        config = Config(db)
        from web.app import WebDashboard
        dash = WebDashboard(db, config, port=port, logger=log)
        dash.start()
        print(f"  Web dashboard running at http://0.0.0.0:{port}")
        print("  Press Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n  Stopping...")
            dash.stop()
            db.close()
        return

    tui = TUI()
    tui.run()


if __name__ == "__main__":
    main()
