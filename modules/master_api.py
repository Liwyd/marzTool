import json
import logging
import secrets
import threading
from datetime import datetime, timezone

try:
    from flask import Flask, request, jsonify
except ImportError:
    Flask = None
    request = None
    jsonify = None


class MasterAPI:
    def __init__(self, db, port: int = 8888, logger=None):
        self.db = db
        self.port = port
        self.log = logger or logging.getLogger("master_api")
        self.app = None
        self._thread = None

    def _build_app(self):
        if Flask is None:
            raise ImportError("Flask not installed. Run: pip install flask")
        app = Flask(__name__)
        db = self.db

        @app.route("/api/nodes", methods=["POST"])
        def register_node():
            data = request.get_json(force=True)
            name = data.get("name", "").strip()
            url = data.get("url", "").strip()
            if not name or not url:
                return jsonify({"error": "name and url required"}), 400
            token = secrets.token_hex(16)
            node_id = db.add_node(name, url, token)
            db.update_node_last_seen(node_id)
            self.log.info("Node registered: %s (id=%d)", name, node_id)
            return jsonify({"node_id": node_id, "token": token})

        @app.route("/api/nodes", methods=["GET"])
        def list_nodes():
            nodes = db.get_all_nodes()
            return jsonify({"nodes": nodes})

        @app.route("/api/nodes/<int:node_id>", methods=["DELETE"])
        def delete_node(node_id):
            db.remove_node(node_id)
            self.log.info("Node removed: id=%d", node_id)
            return jsonify({"ok": True})

        @app.route("/api/config", methods=["GET"])
        def get_config():
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            node = db.get_node_by_token(token)
            if not node:
                return jsonify({"error": "invalid token"}), 401
            db.update_node_last_seen(node["id"])
            config = db.get_master_settings()
            return jsonify(config)

        @app.route("/api/data", methods=["POST"])
        def push_data():
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            node = db.get_node_by_token(token)
            if not node:
                return jsonify({"error": "invalid token"}), 401
            db.update_node_last_seen(node["id"])
            data = request.get_json(force=True)
            data_type = data.get("type", "")
            data_payload = data.get("data", {})
            if data_type not in ("counter", "vcounter", "volume", "status"):
                return jsonify({"error": "invalid data type"}), 400
            db.upsert_node_data(node["id"], data_type, json.dumps(data_payload))
            return jsonify({"ok": True})

        @app.route("/api/dashboard", methods=["GET"])
        def dashboard():
            counter_data = db.get_all_node_data("counter")
            vcounter_data = db.get_all_node_data("vcounter")
            volume_data = db.get_all_node_data("volume")
            status_data = db.get_all_node_data("status")

            nodes = db.get_all_nodes()
            node_map = {n["id"]: n for n in nodes}

            result = {
                "nodes": [],
                "summary": {
                    "total_counter": 0,
                    "total_vcounter_bytes": 0,
                    "total_volume_users_disabled": 0,
                },
            }

            node_stats = {}
            for n in nodes:
                node_stats[n["id"]] = {
                    "id": n["id"],
                    "name": n["name"],
                    "url": n["url"],
                    "last_seen": n["last_seen"],
                    "online": False,
                    "counter": {},
                    "vcounter": {},
                    "volume": {},
                    "status": {},
                }
                if n["last_seen"]:
                    try:
                        seen = datetime.fromisoformat(n["last_seen"])
                        delta = datetime.now(timezone.utc) - seen
                        node_stats[n["id"]]["online"] = delta.total_seconds() < 120
                    except Exception:
                        pass

            for entry in counter_data:
                nid = entry["node_id"]
                if nid in node_stats:
                    try:
                        node_stats[nid]["counter"] = json.loads(entry["data_json"])
                    except Exception:
                        pass

            for entry in vcounter_data:
                nid = entry["node_id"]
                if nid in node_stats:
                    try:
                        node_stats[nid]["vcounter"] = json.loads(entry["data_json"])
                    except Exception:
                        pass

            for entry in volume_data:
                nid = entry["node_id"]
                if nid in node_stats:
                    try:
                        node_stats[nid]["volume"] = json.loads(entry["data_json"])
                    except Exception:
                        pass

            for entry in status_data:
                nid = entry["node_id"]
                if nid in node_stats:
                    try:
                        node_stats[nid]["status"] = json.loads(entry["data_json"])
                    except Exception:
                        pass

            for ns in node_stats.values():
                ct = ns["counter"].get("total", 0)
                vc = ns["vcounter"].get("total_bytes", 0)
                vl = ns["volume"].get("disabled_count", 0)
                result["summary"]["total_counter"] += ct
                result["summary"]["total_vcounter_bytes"] += vc
                result["summary"]["total_volume_users_disabled"] += vl
                result["nodes"].append(ns)

            return jsonify(result)

        @app.route("/api/ping", methods=["GET"])
        def ping():
            return jsonify({"ok": True, "role": "master"})

        return app

    def start(self):
        if Flask is None:
            self.log.error("Flask not installed. Master API disabled. pip install flask")
            return False
        self.app = self._build_app()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.log.info("Master API started on port %d", self.port)
        return True

    def _run(self):
        import werkzeug.serving
        log = werkzeug.serving.WSGIRequestHandler
        log.log_request = lambda *a, **kw: None
        self.app.run(host="0.0.0.0", port=self.port, debug=False, use_reloader=False)

    def stop(self):
        self.log.info("Master API stopping.")


def start_master_api(db, port: int = 8888, logger=None) -> MasterAPI:
    api = MasterAPI(db, port=port, logger=logger)
    api.start()
    return api
