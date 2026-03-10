import uuid
import json
import requests
from datetime import datetime, timedelta
from config import XUI_HOST, XUI_USERNAME, XUI_PASSWORD, XUI_INBOUND_ID
import time
import logging

log = logging.getLogger(__name__)


class XUIClient:
    def __init__(self):
        self.host = XUI_HOST.rstrip("/")
        self.username = XUI_USERNAME
        self.password = XUI_PASSWORD
        self.inbound_id = XUI_INBOUND_ID
        self.session = requests.Session()
        self._logged_in = False

    def _retry_request(self, func, *args, **kwargs):
        """Retry request up to 3 times on failure."""
        for attempt in range(3):
            try:
                return func(*args, **kwargs)
            except (requests.RequestException, Exception) as e:
                if attempt == 2:
                    raise e
                log.warning(f"Request failed (attempt {attempt+1}): {e}")
                time.sleep(1)
                self._logged_in = False  # Force re-login

    def _login(self):
        def login():
            url = f"{self.host}/login"
            resp = self.session.post(url, json={
                "username": self.username,
                "password": self.password
            }, timeout=10)
            data = resp.json()
            if data.get("success"):
                self._logged_in = True
                return True
            raise Exception(f"3x-ui login failed: {data.get('msg', 'Unknown error')}")
        return self._retry_request(login)

    def _ensure_login(self):
        if not self._logged_in:
            self._login()

    def get_inbound(self):
        """Get inbound info including all clients."""
        def get():
            self._ensure_login()
            url = f"{self.host}/panel/api/inbounds/get/{self.inbound_id}"
            resp = self.session.get(url, timeout=10)
            data = resp.json()
            if not data.get("success"):
                raise Exception(f"Failed to get inbound: {data.get('msg')}")
            return data["obj"]
        return self._retry_request(get)

    def add_client(self, email: str, days: int, traffic_gb: int = 50) -> dict:
        """
        Create a new client in the inbound.
        Returns dict with client_id, email, link.
        """
        def add():
            self._ensure_login()

            client_id = str(uuid.uuid4())
            expire_ms = int((datetime.now() + timedelta(days=days)).timestamp() * 1000)
            traffic_bytes = traffic_gb * 1024 ** 3

            inbound = self.get_inbound()
            protocol = inbound.get("protocol", "vless")

            client_payload = {
                "id": client_id,
                "email": email,
                "enable": True,
                "expiryTime": expire_ms,
                "totalGB": traffic_bytes,
                "limitIp": 0,
                "tgId": "",
                "subId": ""
            }
            if protocol == "vmess":
                client_payload["alterId"] = 0

            url = f"{self.host}/panel/api/inbounds/addClient"
            payload = {
                "id": self.inbound_id,
                "settings": json.dumps({"clients": [client_payload]})
            }
            resp = self.session.post(url, json=payload, timeout=10)
            data = resp.json()
            if not data.get("success"):
                raise Exception(f"Failed to add client: {data.get('msg')}")

            link = self._build_link(inbound, client_id, email, protocol)
            expire_dt = datetime.fromtimestamp(expire_ms / 1000)

            return {
                "client_id": client_id,
                "email": email,
                "link": link,
                "expire_at": expire_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "protocol": protocol,
            }
        return self._retry_request(add)

    def get_client_traffic(self, email: str) -> dict:
        """Get traffic statistics for a client by email."""
        self._ensure_login()
        url = f"{self.host}/panel/api/inbounds/getClientTraffics/{email}"
        resp = self.session.get(url, timeout=10)
        data = resp.json()
        if not data.get("success"):
            return {"up": 0, "down": 0, "total": 0, "enable": False, "expiryTime": 0}
        obj = data.get("obj") or {}
        return {
            "up": obj.get("up", 0),
            "down": obj.get("down", 0),
            "total": obj.get("total", 0),
            "enable": obj.get("enable", False),
            "expiryTime": obj.get("expiryTime", 0),
        }

    def delete_client(self, client_id: str) -> bool:
        """Delete a client from the inbound."""
        def delete():
            self._ensure_login()
            url = f"{self.host}/panel/api/inbounds/{self.inbound_id}/delClient/{client_id}"
            resp = self.session.post(url, timeout=10)
            data = resp.json()
            return data.get("success", False)
        return self._retry_request(delete)

    def _build_link(self, inbound: dict, client_id: str, email: str, protocol: str) -> str:
        """Build VLESS or VMess connection link."""
        settings = json.loads(inbound.get("settings", "{}"))
        stream = json.loads(inbound.get("streamSettings", "{}"))
        port = inbound.get("port", 443)
        network = stream.get("network", "tcp")
        security = stream.get("security", "none")
        host_domain = self.host.split("//")[-1].split(":")[0]

        if protocol == "vless":
            params = f"type={network}&security={security}"
            if security == "tls":
                sni = stream.get("tlsSettings", {}).get("serverName", host_domain)
                params += f"&sni={sni}"
            if network == "ws":
                ws_path = stream.get("wsSettings", {}).get("path", "/")
                params += f"&path={ws_path}"
            link = f"vless://{client_id}@{host_domain}:{port}?{params}#{email}"
            return link

        elif protocol == "vmess":
            vmess_obj = {
                "v": "2",
                "ps": email,
                "add": host_domain,
                "port": str(port),
                "id": client_id,
                "aid": "0",
                "scy": "auto",
                "net": network,
                "type": "none",
                "host": "",
                "path": stream.get("wsSettings", {}).get("path", "/") if network == "ws" else "",
                "tls": security,
                "sni": "",
                "alpn": "",
                "fp": ""
            }
            import base64
            encoded = base64.b64encode(json.dumps(vmess_obj).encode()).decode()
            return f"vmess://{encoded}"

        return "Unsupported protocol"


# Singleton
xui = XUIClient()
