import logging
import requests


class FlowSetter:
    FLOW_VALUE = "xtls-rprx-vision"
    FLOW_NONE = ""

    def __init__(self, client, logger: logging.Logger = None):
        self.client = client
        self.log = logger or logging.getLogger("flow_setter")

    @staticmethod
    def needs_update(user: dict, target_flow: str) -> bool:
        proxies = user.get("proxies") or {}
        if "vless" not in proxies:
            return False
        return (proxies["vless"] or {}).get("flow", "") != target_flow

    def apply_flow(self, user: dict, target_flow: str) -> tuple[bool, str]:
        proxies = user.get("proxies") or {}
        if "vless" not in proxies:
            return False, "no vless proxy"

        vless = dict(proxies["vless"] or {})
        current = vless.get("flow", "")
        if current == target_flow:
            return False, "flow already correct"

        vless["flow"] = target_flow
        new_proxies = {**proxies, "vless": vless}

        payload: dict = {"proxies": new_proxies}

        if "inbounds" in user:
            payload["inbounds"] = user["inbounds"]

        ALLOWED_STATUSES = {"active", "disabled", "on_hold"}
        for field in (
            "expire", "data_limit", "data_limit_reset_strategy",
            "note", "on_hold_expire_duration",
            "on_hold_timeout", "auto_delete_in_days", "next_plan",
        ):
            if user.get(field) is not None:
                payload[field] = user[field]

        user_status = user.get("status")
        if user_status in ALLOWED_STATUSES:
            payload["status"] = user_status

        result = self.client.put_user(user["username"], payload)
        actual = (result.get("proxies", {}).get("vless") or {}).get("flow", "empty")
        return True, f"flow -> '{actual}'"

    def process_cycle(self, target_flow: str, users: list = None) -> tuple[int, int, list, list]:
        if users is None:
            users = self.client.get_all_users()
        candidates = [u for u in users if self.needs_update(u, target_flow)]
        updated, errors = [], []
        for u in candidates:
            uname = u["username"]
            try:
                changed, msg = self.apply_flow(u, target_flow)
                if changed:
                    updated.append(uname)
                    self.log.info("  UPDATED   %-32s  %s", uname, msg)
            except requests.HTTPError as e:
                errors.append(uname)
                body = ""
                try:
                    body = e.response.text[:300]
                except Exception:
                    pass
                self.log.error("  ERROR     %-32s  HTTP %s  %s", uname, e.response.status_code, body)
            except Exception as e:
                errors.append(uname)
                self.log.error("  ERROR     %-32s  %s", uname, e)
        return len(users), len(candidates), updated, errors

    def run_once(self, target_flow: str) -> tuple[int, int, list, list]:
        label = f"'{self.FLOW_VALUE}'" if target_flow == self.FLOW_VALUE else "none / empty"
        self.log.info("Flow setter: target=%s", label)
        return self.process_cycle(target_flow)
