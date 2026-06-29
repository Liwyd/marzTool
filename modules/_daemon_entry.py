import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.daemon import _daemon_worker, CONFIG_FILE

if __name__ == "__main__":
    if CONFIG_FILE.exists():
        config_dict = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        _daemon_worker(config_dict)
    else:
        print("No config file found.")
        sys.exit(1)
