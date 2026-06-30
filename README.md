# MarzTool

Marzban Management Suite - a unified tool for managing Marzban panels with multi-server support.

## Features

- **VLESS Flow Management** - Set/clear `xtls-rprx-vision` flow on all users
- **IP Limiting** - Automatic IP limiting per user with iptables banning
- **Counter** - Track users per admin (500MB threshold, 7-day expire gap)
- **VCounter** - Track volume per admin with anti-cheat rules
- **Volume Limiter** - Disable users exceeding configurable GB limit
- **Telegram Bot** - Full-featured bot with inline keyboard menus
- **Multi-Server** - Master/node architecture for managing multiple Marzban servers

## Quick Install (Linux)

```bash
curl -sSL https://raw.githubusercontent.com/liwyd/marzTool/main/install.sh | bash
```

Or clone manually:

```bash
git clone https://github.com/liwyd/marzTool.git /opt/marztool
cd /opt/marztool
pip install requests
python3 marzTool.py
```

## Usage

```bash
python3 marzTool.py          # Interactive TUI
python3 marzTool.py --auto   # Start daemon with saved settings
python3 marzTool.py --stop   # Stop daemon
python3 marzTool.py --logs   # View daemon logs
python3 marzTool.py --master # Start master API server
```

## Multi-Server Architecture

### Master Mode
- Runs an HTTP API server (default port 8888)
- Aggregates counter/vcounter/volume data from all nodes
- Pushes config updates to nodes
- View aggregated dashboard in TUI

### Node Mode
- Connects to master for config overrides
- Pushes local data (counter/vcounter/volume) to master
- Runs independently if master is unreachable
- Full TUI and daemon like standalone mode

### Setup

1. **Master**: Install on one server, run TUI, configure Master/Node > Master mode
2. **Nodes**: Install on other servers, run TUI, configure Master/Node > Node mode with master URL
3. **Daemon**: Start daemon on all servers (`python3 marzTool.py --auto`)

## Requirements

- Python 3.10+
- `requests` library
- `flask` (only for master mode)
- `python-telegram-bot` (optional, for Telegram bot)
- Linux: `iptables` for IP limiting

## Configuration

All settings stored in SQLite database (`marztool.db`). Configure via TUI:

- Server URL and credentials
- Flow mode (set/clear)
- IP limiting
- Counter/VCounter (mutually exclusive)
- Volume limit
- Telegram bot
- Master/Node mode
