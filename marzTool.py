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
  python marzTool.py --update # update from git repository
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

    if "--uninstall" in args:
        import shutil
        install_dir = os.path.dirname(os.path.abspath(__file__))
        symlink = "/usr/local/bin/marztool"
        temp_dir = "/tmp/marztool"

        print("========================================")
        print("  MarzTool Uninstaller")
        print("========================================")
        print()

        # Stop daemon
        print("  Stopping daemon...")
        stop_daemon()

        # Stop web dashboard
        try:
            from modules.web_daemon import stop_web_daemon, web_daemon_pid
            if web_daemon_pid():
                stop_web_daemon()
                print("  Web dashboard stopped.")
        except Exception:
            pass

        # Kill any lingering processes (exclude current PID)
        import subprocess
        current_pid = str(os.getpid())
        try:
            result = subprocess.run(
                ["pgrep", "-f", "marztool|_daemon_entry|_web_entry"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                for pid in result.stdout.strip().split("\n"):
                    if pid == current_pid:
                        continue
                    try:
                        os.kill(int(pid), 9)
                    except Exception:
                        pass
                print("  Remaining processes killed.")
        except Exception:
            pass

        # Remove symlink
        if os.path.exists(symlink):
            os.remove(symlink)
            print(f"  Removed: {symlink}")

        # Remove temp directory
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"  Removed: {temp_dir}")

        # Remove install directory (last, since we're running from it)
        print(f"  Removing: {install_dir}")
        print()
        print("  MarzTool has been completely uninstalled.")
        print()

        # Self-delete: schedule removal after exit
        import atexit
        def _self_remove():
            try:
                shutil.rmtree(install_dir, ignore_errors=True)
            except Exception:
                pass
        atexit.register(_self_remove)
        sys.exit(0)

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

    if "--update" in args:
        import subprocess
        install_dir = os.path.dirname(os.path.abspath(__file__))
        print("  Updating MarzTool...")
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=install_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
            if result.returncode == 0:
                print("  Update complete. Restart daemon if running.")
            else:
                print("  Update failed.")
        except Exception as e:
            print(f"  Update error: {e}")
        return

    tui = TUI()
    tui.run()


if __name__ == "__main__":
    main()
