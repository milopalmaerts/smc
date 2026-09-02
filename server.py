from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from bot import bot


ROOT = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload: bytes, content_type: str = "application/json", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._send(json.dumps(bot.snapshot()).encode())
            return
        files = {"/": ("static/index.html", "text/html"), "/app.js": ("static/app.js", "text/javascript"), "/styles.css": ("static/styles.css", "text/css")}
        if path in files:
            filename, content_type = files[path]
            self._send((ROOT / filename).read_bytes(), content_type)
            return
        self._send(b"Not found", "text/plain", 404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/config":
            self._send(b"Not found", "text/plain", 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            values = json.loads(self.rfile.read(length) or b"{}")
            bot.update_config(values)
            self._send(json.dumps(bot.snapshot()).encode())
        except (ValueError, TypeError, json.JSONDecodeError):
            self._send(b"Invalid JSON", "text/plain", 400)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"SupplyDemand bot running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
