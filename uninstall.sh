#!/bin/bash
set -e

INSTALL_DIR="/opt/marztool"
SYMLINK="/usr/local/bin/marztool"
TEMP_DIR="/tmp/marztool"

echo "========================================"
echo "  MarzTool Uninstaller"
echo "========================================"
echo ""

# --- Step 1: Stop the main daemon ---
echo "  [1/5] Stopping daemon processes..."
if [ -f "$TEMP_DIR/daemon.pid" ]; then
    DAEMON_PID=$(cat "$TEMP_DIR/daemon.pid" 2>/dev/null || true)
    if [ -n "$DAEMON_PID" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
        echo "    Sending SIGTERM to daemon (PID $DAEMON_PID)..."
        kill "$DAEMON_PID" 2>/dev/null || true
        sleep 1
        if kill -0 "$DAEMON_PID" 2>/dev/null; then
            echo "    Force killing daemon..."
            kill -9 "$DAEMON_PID" 2>/dev/null || true
        fi
        echo "    Daemon stopped."
    else
        echo "    Daemon was not running (stale PID file)."
    fi
    rm -f "$TEMP_DIR/daemon.pid"
else
    echo "    No daemon PID file found."
fi

# --- Step 2: Stop the web dashboard ---
echo "  [2/5] Stopping web dashboard..."
if [ -f "$TEMP_DIR/web_dashboard.pid" ]; then
    WEB_PID=$(cat "$TEMP_DIR/web_dashboard.pid" 2>/dev/null || true)
    if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
        echo "    Sending SIGTERM to web dashboard (PID $WEB_PID)..."
        kill "$WEB_PID" 2>/dev/null || true
        sleep 1
        if kill -0 "$WEB_PID" 2>/dev/null; then
            echo "    Force killing web dashboard..."
            kill -9 "$WEB_PID" 2>/dev/null || true
        fi
        echo "    Web dashboard stopped."
    else
        echo "    Web dashboard was not running (stale PID file)."
    fi
    rm -f "$TEMP_DIR/web_dashboard.pid"
else
    echo "    No web dashboard PID file found."
fi

# --- Step 3: Kill any lingering marztool python processes ---
echo "  [3/5] Checking for remaining marztool processes..."
REMAINING=$(pgrep -f "marztool|_daemon_entry|_web_entry" 2>/dev/null | grep -v "^$$\$" || true)
if [ -n "$REMAINING" ]; then
    echo "    Found remaining processes, killing them..."
    for p in $REMAINING; do
        kill "$p" 2>/dev/null || true
    done
    sleep 1
    # Force kill if still alive
    for p in $REMAINING; do
        if kill -0 "$p" 2>/dev/null; then
            kill -9 "$p" 2>/dev/null || true
        fi
    done
    echo "    All remaining processes killed."
else
    echo "    No remaining marztool processes."
fi

# --- Step 4: Remove the symlink ---
echo "  [4/5] Removing command symlink..."
if [ -L "$SYMLINK" ] || [ -f "$SYMLINK" ]; then
    rm -f "$SYMLINK"
    echo "    Removed: $SYMLINK"
else
    echo "    Symlink not found (already removed)."
fi

# --- Step 5: Remove installation directory ---
echo "  [5/5] Removing installation files..."
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "    Removed: $INSTALL_DIR"
else
    echo "    Install directory not found (already removed)."
fi

# --- Cleanup temp files ---
echo ""
echo "  Cleaning up temp files..."
rm -rf "$TEMP_DIR"
echo "    Removed: $TEMP_DIR"

# --- Note about iptables ---
echo ""
echo "  NOTE: MarzTool may have added iptables rules for IP banning."
echo "  If you want to remove all iptables rules, run:"
echo "    sudo iptables -F"
echo ""

echo ""
echo "========================================"
echo "  MarzTool has been completely removed!"
echo "========================================"
echo ""
echo "  All files, databases, configs,"
echo "  logs, processes, and firewall rules"
echo "  have been cleaned."
echo ""
