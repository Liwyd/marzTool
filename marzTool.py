#!/usr/bin/env python3
"""
MarzTool - Marzban Management Suite

A unified tool for managing Marzban panels with features:
  - VLESS Flow management (set/clear xtls-rprx-vision)
  - IP limiting per user with automatic banning
  - Unified daemon for background operation
  - Telegram bot integration

Usage:
  python marzTool.py          # interactive TUI
  python marzTool.py --auto   # start daemon with current settings
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

    tui = TUI()
    tui.run()


if __name__ == "__main__":
    main()
