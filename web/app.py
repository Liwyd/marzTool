import json
import logging
import sys
import os
import threading
import time
from datetime import datetime, timezone

try:
    from flask import Flask, jsonify, request, render_template, send_from_directory
except ImportError:
    Flask = None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.database import Database
from modules.config import Config
from modules.api_client import MarzbanClient


class WebDashboard:
    def __init__(self, db: Database, config: Config, port: int = 8080, logger=None):
        self.db = db
        self.config = config
        self.port = port
        self.log = logger or logging.getLogger("web_dashboard")
        self.app = None
        self._thread = None
        self._client = None

    def _get_client(self) -> MarzbanClient | None:
        url = self.config.get_server_url()
        username = self.config.get_username()
        password = self.config.get_password()
        if not url or not username or not password:
            return None
        try:
            if self._client is None:
                self._client = MarzbanClient(url, self.log)
            self._client.login(username, password)
            return self._client
        except Exception as e:
            self.log.error("Marzban login failed: %s", e)
            self._client = None
            return None

    def _build_app(self) -> Flask:
        app = Flask(__name__, static_folder="static", template_folder="templates")
        dash = self
        db = self.db
        config = self.config

        @app.route("/")
        def index():
            return render_template("index.html")

        @app.route("/api/summary")
        def api_summary():
            client = dash._get_client()
            users = []
            if client:
                try:
                    users = client.get_all_users()
                except Exception:
                    pass

            total_users = len(users)
            active_users = sum(1 for u in users if u.get("status") == "active")
            admins = {}
            for u in users:
                a = u.get("admin")
                if a and a.get("username"):
                    admins[a["username"]] = admins.get(a["username"], 0) + 1

            counter_totals = db.get_all_counter_totals()
            vcounter_totals = db.get_all_vcounter_totals()
            exempt_count = len(db.get_all_exempt_users())

            return jsonify({
                "total_users": total_users,
                "active_users": active_users,
                "admin_count": len(admins),
                "admins": admins,
                "counter_totals": counter_totals,
                "vcounter_totals": vcounter_totals,
                "exempt_count": exempt_count,
                "features": {
                    "flow": config.get_flow_enabled(),
                    "ip_limit": config.get_ip_limit_enabled(),
                    "counter": config.get_counter_enabled(),
                    "vcounter": config.get_vcounter_enabled(),
                    "volume_limit": config.get_volume_limit_enabled(),
                    "telegram": config.get_telegram_enabled(),
                },
                "server_url": config.get_server_url() or "",
            })

        @app.route("/api/counter/report")
        def api_counter_report():
            viewer = request.args.get("viewer", "web")
            report = CounterView.get_report(db, viewer=viewer)
            return jsonify(report)

        @app.route("/api/counter/settle", methods=["POST"])
        def api_counter_settle():
            data = request.get_json(force=True)
            admin_username = data.get("admin_username")
            settled_by = data.get("settled_by", "web")
            if not admin_username:
                return jsonify({"error": "admin_username required"}), 400
            from modules.counter import Counter
            counter = Counter(None, db)
            settled = counter.settle(admin_username, settled_by)
            return jsonify({"settled": settled})

        @app.route("/api/counter/settlements")
        def api_counter_settlements():
            admin = request.args.get("admin")
            settlements = db.get_counter_settlements(admin)
            return jsonify({"settlements": settlements})

        @app.route("/api/counter/reset", methods=["POST"])
        def api_counter_reset():
            data = request.get_json(force=True)
            admin = data.get("admin_username")
            from modules.counter import Counter
            counter = Counter(None, db)
            counter.reset(admin)
            return jsonify({"ok": True})

        @app.route("/api/vcounter/report")
        def api_vcounter_report():
            viewer = request.args.get("viewer", "web")
            from modules.vcounter import VCounter
            vc = VCounter(None, db)
            report = vc.get_report(viewer=viewer)
            return jsonify(report)

        @app.route("/api/vcounter/settle", methods=["POST"])
        def api_vcounter_settle():
            data = request.get_json(force=True)
            admin_username = data.get("admin_username")
            settled_by = data.get("settled_by", "web")
            if not admin_username:
                return jsonify({"error": "admin_username required"}), 400
            from modules.vcounter import VCounter
            vc = VCounter(None, db)
            settled = vc.settle(admin_username, settled_by)
            return jsonify({"settled": settled})

        @app.route("/api/vcounter/settlements")
        def api_vcounter_settlements():
            admin = request.args.get("admin")
            settlements = db.get_vcounter_settlements(admin)
            return jsonify({"settlements": settlements})

        @app.route("/api/ip/limits")
        def api_ip_limits():
            limits = db.get_all_ip_limits()
            return jsonify({"limits": limits})

        @app.route("/api/ip/set", methods=["POST"])
        def api_ip_set():
            data = request.get_json(force=True)
            username = data.get("username")
            limit = data.get("limit")
            if not username or limit is None:
                return jsonify({"error": "username and limit required"}), 400
            db.set_ip_limit(username, int(limit))
            return jsonify({"ok": True})

        @app.route("/api/ip/delete", methods=["POST"])
        def api_ip_delete():
            data = request.get_json(force=True)
            username = data.get("username")
            if not username:
                return jsonify({"error": "username required"}), 400
            db.delete_ip_limit(username)
            return jsonify({"ok": True})

        @app.route("/api/flow/set", methods=["POST"])
        def api_flow_set():
            client = dash._get_client()
            if not client:
                return jsonify({"error": "not connected"}), 400
            data = request.get_json(force=True)
            flow_value = data.get("flow_value", "xtls-rprx-vision")
            from modules.flow_setter import FlowSetter
            fs = FlowSetter(client, dash.log)
            total, needed, updated, errors = fs.process_cycle(flow_value)
            return jsonify({
                "total": total, "needed": needed,
                "updated": len(updated), "errors": len(errors),
            })

        @app.route("/api/flow/clear", methods=["POST"])
        def api_flow_clear():
            client = dash._get_client()
            if not client:
                return jsonify({"error": "not connected"}), 400
            from modules.flow_setter import FlowSetter
            fs = FlowSetter(client, dash.log)
            total, needed, updated, errors = fs.process_cycle(FlowSetter.FLOW_NONE)
            return jsonify({
                "total": total, "needed": needed,
                "updated": len(updated), "errors": len(errors),
            })

        @app.route("/api/volume/config", methods=["POST"])
        def api_volume_config():
            data = request.get_json(force=True)
            gb = data.get("limit_gb")
            if gb is not None:
                config.set_volume_limit_gb(int(gb))
            enabled = data.get("enabled")
            if enabled is not None:
                config.set_volume_limit_enabled(enabled)
            return jsonify({"ok": True})

        @app.route("/api/volume/exempt")
        def api_volume_exempt():
            exempt = db.get_all_exempt_users()
            return jsonify({"exempt": exempt})

        @app.route("/api/volume/exempt/add", methods=["POST"])
        def api_volume_exempt_add():
            data = request.get_json(force=True)
            username = data.get("username")
            if not username:
                return jsonify({"error": "username required"}), 400
            now = datetime.now(timezone.utc).isoformat()
            db.add_exempt(username, now)
            return jsonify({"ok": True})

        @app.route("/api/volume/exempt/remove", methods=["POST"])
        def api_volume_exempt_remove():
            data = request.get_json(force=True)
            username = data.get("username")
            if not username:
                return jsonify({"error": "username required"}), 400
            db.remove_exempt(username)
            return jsonify({"ok": True})

        @app.route("/api/volume/notifications")
        def api_volume_notifications():
            cursor = db.conn.cursor()
            cursor.execute(
                "SELECT id, username, admin_username, used_traffic_bytes, disabled_at "
                "FROM volume_limit_notifications ORDER BY disabled_at DESC LIMIT 50"
            )
            rows = cursor.fetchall()
            notifs = [
                {"id": r[0], "username": r[1], "admin_username": r[2],
                 "used_traffic_bytes": r[3], "disabled_at": r[4]}
                for r in rows
            ]
            return jsonify({"notifications": notifs})

        @app.route("/api/subadmin/counter")
        def api_subadmin_counter():
            subs = db.get_all_sub_admins()
            return jsonify({"sub_admins": subs})

        @app.route("/api/subadmin/counter/add", methods=["POST"])
        def api_subadmin_counter_add():
            data = request.get_json(force=True)
            telegram_id = data.get("telegram_id")
            allowed = data.get("allowed_admins", [])
            if not telegram_id:
                return jsonify({"error": "telegram_id required"}), 400
            db.add_sub_admin(int(telegram_id), allowed)
            return jsonify({"ok": True})

        @app.route("/api/subadmin/counter/remove", methods=["POST"])
        def api_subadmin_counter_remove():
            data = request.get_json(force=True)
            telegram_id = data.get("telegram_id")
            if not telegram_id:
                return jsonify({"error": "telegram_id required"}), 400
            db.remove_sub_admin(int(telegram_id))
            return jsonify({"ok": True})

        @app.route("/api/subadmin/vcounter")
        def api_subadmin_vcounter():
            subs = db.get_all_vcounter_sub_admins()
            return jsonify({"sub_admins": subs})

        @app.route("/api/subadmin/vcounter/add", methods=["POST"])
        def api_subadmin_vcounter_add():
            data = request.get_json(force=True)
            telegram_id = data.get("telegram_id")
            allowed = data.get("allowed_admins", [])
            if not telegram_id:
                return jsonify({"error": "telegram_id required"}), 400
            db.add_vcounter_sub_admin(int(telegram_id), allowed)
            return jsonify({"ok": True})

        @app.route("/api/subadmin/vcounter/remove", methods=["POST"])
        def api_subadmin_vcounter_remove():
            data = request.get_json(force=True)
            telegram_id = data.get("telegram_id")
            if not telegram_id:
                return jsonify({"error": "telegram_id required"}), 400
            db.remove_vcounter_sub_admin(int(telegram_id))
            return jsonify({"ok": True})

        @app.route("/api/telegram/test", methods=["POST"])
        def api_telegram_test():
            from modules.telegram_bot import TelegramBot
            bot = TelegramBot(config)
            ok, msg = bot.test_connection()
            return jsonify({"ok": ok, "message": msg})

        @app.route("/api/settings", methods=["GET"])
        def api_settings_get():
            return jsonify({
                "server_url": config.get_server_url() or "",
                "username": config.get_username() or "",
                "flow_value": config.get_flow_value(),
                "flow_enabled": config.get_flow_enabled(),
                "ip_limit_enabled": config.get_ip_limit_enabled(),
                "ip_limit_all": config.get_ip_limit_all(),
                "counter_enabled": config.get_counter_enabled(),
                "vcounter_enabled": config.get_vcounter_enabled(),
                "volume_limit_enabled": config.get_volume_limit_enabled(),
                "volume_limit_gb": config.get_volume_limit_gb(),
                "telegram_enabled": config.get_telegram_enabled(),
                "telegram_token": config.get_telegram_token() or "",
                "telegram_admin_id": config.get_telegram_admin_id() or "",
                "daemon_interval": config.get_daemon_interval(),
                "ban_time": config.get_ban_time(),
                "ssh_port": config.get_ssh_port(),
                "master_enabled": config.get_master_enabled(),
                "master_port": config.get_master_port(),
                "node_enabled": config.get_node_enabled(),
                "node_name": config.get_node_name() or "",
                "master_url": config.get_master_url() or "",
            })

        @app.route("/api/settings", methods=["POST"])
        def api_settings_post():
            data = request.get_json(force=True)
            if "server_url" in data:
                config.set_server_url(data["server_url"])
            if "username" in data:
                config.set_username(data["username"])
            if "password" in data:
                config.set_password(data["password"])
            if "flow_value" in data:
                config.set_flow_value(data["flow_value"])
            if "flow_enabled" in data:
                config.set_flow_enabled(data["flow_enabled"])
            if "ip_limit_enabled" in data:
                config.set_ip_limit_enabled(data["ip_limit_enabled"])
            if "ip_limit_all" in data:
                config.set_ip_limit_all(int(data["ip_limit_all"]))
            if "counter_enabled" in data:
                config.set_counter_enabled(data["counter_enabled"])
            if "vcounter_enabled" in data:
                config.set_vcounter_enabled(data["vcounter_enabled"])
            if "volume_limit_enabled" in data:
                config.set_volume_limit_enabled(data["volume_limit_enabled"])
            if "volume_limit_gb" in data:
                config.set_volume_limit_gb(int(data["volume_limit_gb"]))
            if "telegram_enabled" in data:
                config.set_telegram_enabled(data["telegram_enabled"])
            if "telegram_token" in data:
                config.set_telegram_token(data["telegram_token"])
            if "telegram_admin_id" in data:
                config.set_telegram_admin_id(data["telegram_admin_id"])
            if "daemon_interval" in data:
                config.set_daemon_interval(int(data["daemon_interval"]))
            if "ban_time" in data:
                config.set_ban_time(int(data["ban_time"]))
            if "ssh_port" in data:
                config.set_ssh_port(int(data["ssh_port"]))
            return jsonify({"ok": True})

        @app.route("/api/daemon/status")
        def api_daemon_status():
            from modules.daemon import daemon_pid
            pid = daemon_pid()
            return jsonify({"running": pid is not None, "pid": pid})

        @app.route("/api/daemon/start", methods=["POST"])
        def api_daemon_start():
            from modules.daemon import spawn_daemon
            pid = spawn_daemon(config)
            return jsonify({"ok": True, "pid": pid})

        @app.route("/api/daemon/stop", methods=["POST"])
        def api_daemon_stop():
            from modules.daemon import stop_daemon
            stop_daemon()
            return jsonify({"ok": True})

        @app.route("/api/daemon/logs")
        def api_daemon_logs():
            from modules.daemon import LOG_FILE
            lines = int(request.args.get("lines", 50))
            if not LOG_FILE.exists():
                return jsonify({"logs": ""})
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            return jsonify({"logs": "".join(all_lines[-lines:])})

        @app.route("/api/users")
        def api_users():
            client = dash._get_client()
            if not client:
                return jsonify({"error": "not connected"}), 400
            users = client.get_all_users()
            result = []
            for u in users:
                a = u.get("admin") or {}
                result.append({
                    "username": u.get("username", ""),
                    "status": u.get("status", ""),
                    "data_limit": u.get("data_limit", 0),
                    "used_traffic": u.get("used_traffic", 0),
                    "lifetime_used_traffic": u.get("lifetime_used_traffic", 0),
                    "admin": a.get("username", ""),
                    "created_at": u.get("created_at", ""),
                    "expire": u.get("expire"),
                })
            return jsonify({"users": result, "total": len(result)})

        @app.route("/api/settings/ssl", methods=["GET"])
        def api_ssl_get():
            return jsonify({
                "ssl_cert": config.get_ssl_cert() or "",
                "ssl_key": config.get_ssl_key() or "",
            })

        @app.route("/api/settings/ssl", methods=["POST"])
        def api_ssl_post():
            data = request.get_json(force=True)
            if "ssl_cert" in data:
                config.set_ssl_cert(data["ssl_cert"])
            if "ssl_key" in data:
                config.set_ssl_key(data["ssl_key"])
            return jsonify({"ok": True})

        @app.route("/api/ssl/get", methods=["POST"])
        def api_ssl_get_cert():
            import subprocess
            data = request.get_json(force=True)
            email = data.get("email", "").strip()
            domain = data.get("domain", "").strip()
            if not email or not domain:
                return jsonify({"ok": False, "error": "email and domain required"}), 400

            cert_dir = f"/opt/marztool/certs/{domain}"
            os.makedirs(cert_dir, exist_ok=True)

            def _run_ssl():
                acme = os.path.expanduser("~/.acme.sh/acme.sh")
                used = "acme.sh"

                if not os.path.exists(acme):
                    r = subprocess.run(
                        ["curl", "-s", "https://get.acme.sh", "|", "sh", "-s", "email=" + email],
                        shell=True, capture_output=True, text=True, timeout=60,
                    )
                    if not os.path.exists(acme):
                        return None, "Failed to install acme.sh"

                r = subprocess.run(
                    [acme, "--issue", "--standalone", "-d", domain, "--accountemail", email],
                    capture_output=True, text=True, timeout=120,
                )
                if r.returncode != 0:
                    r2 = subprocess.run(
                        ["certbot", "certonly", "--standalone", "-d", domain,
                         "--non-interactive", "--agree-tos", "--email", email],
                        capture_output=True, text=True, timeout=120,
                    )
                    if r2.returncode != 0:
                        return None, f"acme.sh failed: {r.stderr[:200]}\ncertbot failed: {r2.stderr[:200]}"
                    used = "certbot"
                    subprocess.run(
                        ["cp", f"/etc/letsencrypt/live/{domain}/privkey.pem", f"{cert_dir}/privkey.pem"],
                        timeout=10,
                    )
                    subprocess.run(
                        ["cp", f"/etc/letsencrypt/live/{domain}/fullchain.pem", f"{cert_dir}/fullchain.pem"],
                        timeout=10,
                    )
                else:
                    r3 = subprocess.run(
                        [acme, "--install-cert", "-d", domain,
                         "--key-file", f"{cert_dir}/privkey.pem",
                         "--fullchain-file", f"{cert_dir}/fullchain.pem"],
                        capture_output=True, text=True, timeout=60,
                    )
                    if r3.returncode != 0:
                        return None, f"Install cert failed: {r3.stderr[:200]}"

                cert_path = f"{cert_dir}/fullchain.pem"
                key_path = f"{cert_dir}/privkey.pem"
                if os.path.exists(cert_path) and os.path.exists(key_path):
                    config.set_ssl_cert(cert_path)
                    config.set_ssl_key(key_path)
                    config.set_ssl_domain(domain)
                    return {"cert": cert_path, "key": key_path, "used": used}, None
                return None, "Certificate files not found after issuance"

            try:
                result, err = _run_ssl()
                if err:
                    return jsonify({"ok": False, "error": err}), 500
                return jsonify({"ok": True, **result})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        @app.route("/api/web/status")
        def api_web_status():
            from modules.web_daemon import web_daemon_pid, web_daemon_port
            pid = web_daemon_pid()
            port = web_daemon_port()
            return jsonify({"running": pid is not None, "pid": pid, "port": port})

        @app.route("/api/web/start", methods=["POST"])
        def api_web_start():
            from modules.web_daemon import spawn_web_daemon
            pid = spawn_web_daemon(config)
            return jsonify({"ok": True, "pid": pid})

        @app.route("/api/web/stop", methods=["POST"])
        def api_web_stop():
            from modules.web_daemon import stop_web_daemon
            stop_web_daemon()
            return jsonify({"ok": True})

        @app.route("/api/update", methods=["POST"])
        def api_update():
            import subprocess
            install_dir = os.path.join(os.path.dirname(__file__), "..")
            try:
                result = subprocess.run(
                    ["git", "pull"],
                    cwd=install_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return jsonify({
                    "ok": True,
                    "output": result.stdout + result.stderr,
                })
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)})

        return app

    def start(self):
        if Flask is None:
            self.log.error("Flask not installed. pip install flask")
            return False
        self.app = self._build_app()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.log.info("Web dashboard started on port %d", self.port)
        return True

    def _run(self):
        try:
            import werkzeug.serving
            werkzeug.serving.WSGIRequestHandler.log_request = lambda *a, **kw: None
        except Exception:
            pass
        ssl_cert = self.config.get_ssl_cert()
        ssl_key = self.config.get_ssl_key()
        ssl_context = None
        if ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key):
            ssl_context = (ssl_cert, ssl_key)
            self.log.info("SSL enabled with cert=%s", ssl_cert)
        self.app.run(host="0.0.0.0", port=self.port, debug=False, use_reloader=False, ssl_context=ssl_context)

    def stop(self):
        self.log.info("Web dashboard stopping.")


class CounterView:
    @staticmethod
    def get_report(db: Database, viewer: str = "web") -> dict:
        totals = db.get_all_counter_totals()
        for t in totals:
            t["total_count"] = db.get_counter_effective_total(
                t["admin_username"], viewer
            )
        total = sum(t["total_count"] for t in totals)
        return {"admins": totals, "total": total}


def start_web_dashboard(db=None, config=None, port: int = 8080, logger=None) -> WebDashboard:
    if db is None:
        db = Database()
    if config is None:
        config = Config(db)
    dash = WebDashboard(db, config, port=port, logger=logger)
    dash.start()
    return dash
