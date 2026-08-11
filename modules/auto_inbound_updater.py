import logging
import uuid
import requests


class AutoInboundUpdater:
    def __init__(self, client, logger: logging.Logger = None):
        self.client = client
        self.log = logger or logging.getLogger("auto_inbound_updater")

    @staticmethod
    def get_missing_inbounds(reference_inbounds: dict, user_inbounds: dict) -> dict:
        missing = {}
        for proto, tags in reference_inbounds.items():
            user_tags = user_inbounds.get(proto, [])
            missing_tags = [t for t in tags if t not in user_tags]
            if missing_tags:
                missing[proto] = missing_tags
        return missing

    @staticmethod
    def get_missing_protocols(reference_inbounds: dict, user_inbounds: dict) -> list[str]:
        missing = []
        for proto in reference_inbounds:
            if proto not in user_inbounds:
                missing.append(proto)
        return missing

    def apply_inbounds(self, user: dict, reference_inbounds: dict) -> tuple[bool, str]:
        current_inbounds = user.get("inbounds") or {}
        current_proxies = user.get("proxies") or {}

        missing_tags = self.get_missing_inbounds(reference_inbounds, current_inbounds)
        missing_protos = self.get_missing_protocols(reference_inbounds, current_inbounds)

        if not missing_tags and not missing_protos:
            return False, "inbounds already synced"

        merged_inbounds = {}
        for proto in set(list(current_inbounds.keys()) + list(reference_inbounds.keys())):
            existing = current_inbounds.get(proto, [])
            new_tags = reference_inbounds.get(proto, [])
            seen = set()
            combined = []
            for t in existing + new_tags:
                if t not in seen:
                    seen.add(t)
                    combined.append(t)
            merged_inbounds[proto] = combined

        merged_proxies = dict(current_proxies)
        for proto in missing_protos:
            if proto not in merged_proxies:
                new_id = str(uuid.uuid4())
                merged_proxies[proto] = {"id": new_id}
                self.log.info("  NEW PROXY %-32s  %s id=%s", user["username"], proto, new_id)

        payload = {"inbounds": merged_inbounds}
        if missing_protos or missing_tags:
            payload["proxies"] = merged_proxies

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

        self.client.put_user(user["username"], payload)

        added_parts = []
        for proto, tags in missing_tags.items():
            added_parts.append(f"{proto}:[{','.join(tags)}]")
        for proto in missing_protos:
            if proto not in missing_tags:
                added_parts.append(f"{proto} (new protocol)")
        return True, f"added {', '.join(added_parts)}"

    def process_cycle(self, reference_username: str, users: list = None) -> tuple[int, int, list, list]:
        if users is None:
            users = self.client.get_all_users()

        ref_user = None
        for u in users:
            if u["username"] == reference_username:
                ref_user = u
                break
        if ref_user is None:
            try:
                ref_user = self.client.get_user(reference_username)
            except Exception as e:
                self.log.error("Cannot fetch reference user '%s': %s", reference_username, e)
                return len(users), 0, [], [reference_username]

        reference_inbounds = ref_user.get("inbounds") or {}
        if not reference_inbounds:
            self.log.warning("Reference user '%s' has no inbounds configured", reference_username)
            return len(users), 0, [], []

        candidates = [
            u for u in users
            if u["username"] != reference_username
            and (
                self.get_missing_inbounds(reference_inbounds, u.get("inbounds") or {})
                or self.get_missing_protocols(reference_inbounds, u.get("inbounds") or {})
            )
        ]

        updated, errors = [], []
        for u in candidates:
            uname = u["username"]
            try:
                changed, msg = self.apply_inbounds(u, reference_inbounds)
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

    def run_once(self, reference_username: str) -> tuple[int, int, list, list]:
        self.log.info("Auto inbound updater: reference user=%s", reference_username)
        return self.process_cycle(reference_username)
