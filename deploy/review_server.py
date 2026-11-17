"""Run a password-protected review instance with a persistent demo database."""
import base64
import hmac
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import DriveStore, LocalHTTPServer, fleet_server, handler


# The hosted instance demonstrates operations on a small synthetic fleet.
# Training and algorithm tuning remain in the local installation.
LOCAL_ONLY_ACTIONS = {
    "/api/train", "/api/recalibrate", "/api/reference", "/api/settings",
    "/api/import", "/api/research_demo", "/api/reset",
}


def make_review_handler(fleet, drive, origin, user, password):
    expected = b"Basic " + base64.b64encode(f"{user}:{password}".encode())

    class ReviewHandler(handler(fleet, drive)):
        def origin_allowed(self):
            return self.headers.get("Origin") == origin

        def authenticated(self):
            supplied = self.headers.get("Authorization", "").encode("latin-1")
            if hmac.compare_digest(supplied, expected):
                return True
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Sanitation review", charset="UTF-8"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False

        def do_GET(self):
            if urlsplit(self.path).path == "/api/health":
                return self.send({"ok": True})
            if self.authenticated():
                return super().do_GET()

        def do_POST(self):
            if not self.authenticated():
                return
            if urlsplit(self.path).path in LOCAL_ONLY_ACTIONS:
                return self.send({"error": "此操作在本地完整版本中提供。"}, 403)
            return super().do_POST()

    return ReviewHandler


def main():
    origin = os.environ["SANITATION_PUBLIC_ORIGIN"]
    url = urlsplit(origin)
    if url.scheme != "https" or not url.hostname or origin != f"https://{url.netloc}" or url.username is not None:
        raise SystemExit("SANITATION_PUBLIC_ORIGIN must be the HTTPS origin without a trailing slash")
    user = os.environ["SANITATION_REVIEW_USER"]
    password = os.environ["SANITATION_REVIEW_PASSWORD"]
    if not user or ":" in user or len(password) < 16:
        raise SystemExit("Set a review username and a password of at least 16 characters")

    bind = os.environ.get("IP", "127.0.0.1")
    port = int(os.environ["PORT"])
    data_dir = Path(os.environ["SANITATION_REVIEW_DATADIR"]).expanduser()
    fleet_path = data_dir / "fleet.sqlite3"
    is_new = not fleet_path.exists()
    fleet = fleet_server.Store(fleet_path)
    if is_new:
        state = fleet.read()
        state["tasks"] = state["tasks"][:3]
        state["vehicles"] = state["vehicles"][:6]
        state["settings"] = {"iterations": 8, "budget": 3, "exact_every": 0}
        fleet.save(state)
    drive = DriveStore(data_dir / "driving.sqlite3", fleet)

    class ReviewServer(LocalHTTPServer):
        address_family = socket.AF_INET6 if ":" in bind else socket.AF_INET

    with ReviewServer((bind, port), make_review_handler(fleet, drive, origin, user, password)) as app:
        print("Sanitation review instance ready.", flush=True)
        app.serve_forever()


if __name__ == "__main__":
    main()
