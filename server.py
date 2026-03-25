import json
import mimetypes
import os
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "sleep_helper.db"


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state TEXT NOT NULL,
                state_label TEXT NOT NULL,
                music TEXT NOT NULL,
                habit TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/recommendations":
            self.handle_get_recommendations()
            return

        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/recommendations":
            self.handle_create_recommendation()
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def handle_get_recommendations(self):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, state, state_label, music, habit, created_at
                FROM recommendations
                ORDER BY id DESC
                LIMIT 10
                """
            ).fetchall()

        data = [dict(row) for row in rows]
        self.send_json(data)

    def handle_create_recommendation(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, status=HTTPStatus.BAD_REQUEST)
            return

        required_fields = ("state", "stateLabel", "music", "habit")
        if not all(payload.get(field) for field in required_fields):
            self.send_json({"error": "Missing fields"}, status=HTTPStatus.BAD_REQUEST)
            return

        record = (
            payload["state"],
            payload["stateLabel"],
            payload["music"],
            payload["habit"],
            datetime.now(timezone.utc).isoformat(),
        )

        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO recommendations (state, state_label, music, habit, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                record,
            )
            connection.commit()

        self.send_json({"id": cursor.lastrowid}, status=HTTPStatus.CREATED)

    def serve_static(self, request_path: str):
        relative_path = request_path.lstrip("/") or "index.html"
        safe_path = (BASE_DIR / relative_path).resolve()

        if BASE_DIR not in safe_path.parents and safe_path != BASE_DIR / "index.html":
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        if not safe_path.exists() or not safe_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        content_type = mimetypes.guess_type(str(safe_path))[0] or "application/octet-stream"
        with open(safe_path, "rb") as file:
            content = file.read()

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def main():
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    print(f"Server running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
