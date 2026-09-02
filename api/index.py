from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse

from bot import SupplyDemandBot


bot = SupplyDemandBot(start_worker=False)


class handler(BaseHTTPRequestHandler):
    def _send(self, payload: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if urlparse(self.path).path != "/api/status":
            self._send(b'{"error":"Not found"}', 404)
            return
        with bot.lock:
            if bot.running:
                bot._tick()
            self._send(json.dumps(bot.snapshot()).encode())

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/config":
            self._send(b'{"error":"Not found"}', 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            values = json.loads(self.rfile.read(length) or b"{}")
            bot.update_config(values)
            self._send(json.dumps(bot.snapshot()).encode())
        except (ValueError, TypeError, json.JSONDecodeError):
            self._send(b'{"error":"Invalid JSON"}', 400)

    def log_message(self, format: str, *args: object) -> None:
        return
