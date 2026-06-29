import json
import logging
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MarzbanClient:
    def __init__(self, base_url: str, logger: logging.Logger = None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"
        self.session.verify = False
        self.log = logger or logging.getLogger("marzban_client")

    def _flip_scheme(self, url: str) -> str:
        if url.startswith("https://"):
            return "http://" + url[8:]
        return "https://" + url[7:]

    def login(self, username: str, password: str):
        url = f"{self.base_url}/api/admin/token"
        try:
            resp = self.session.post(
                url,
                data={"username": username, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.exceptions.Timeout):
            alt = self._flip_scheme(self.base_url)
            self.base_url = alt
            resp = self.session.post(
                f"{self.base_url}/api/admin/token",
                data={"username": username, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self.session.headers["Authorization"] = f"Bearer {token}"
        return token

    def _get(self, path: str, **kwargs) -> dict:
        resp = self.session.get(f"{self.base_url}{path}", timeout=15, **kwargs)
        if resp.status_code == 401:
            raise PermissionError("Token expired or invalid")
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, payload: dict) -> dict:
        resp = self.session.put(
            f"{self.base_url}{path}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code == 401:
            raise PermissionError("Token expired or invalid")
        resp.raise_for_status()
        return resp.json()

    def get_all_users(self) -> list:
        users, offset, limit = [], 0, 100
        while True:
            data = self._get("/api/users", params={"offset": offset, "limit": limit})
            batch = data["users"]
            users.extend(batch)
            offset += len(batch)
            if offset >= data["total"] or not batch:
                break
        return users

    def get_user(self, username: str) -> dict:
        return self._get(f"/api/user/{username}")

    def put_user(self, username: str, payload: dict) -> dict:
        return self._put(f"/api/user/{username}", payload)
