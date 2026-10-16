#!/usr/bin/env python3
"""할 일 앱 서버: todo.html 을 보여주고, 데이터를 data.json 한 파일에 저장합니다.

127.0.0.1 에서만 열려서 외부에서 직접 접속할 수 없습니다.
다른 기기에서는 Tailscale(tailscale serve)을 통해서만 접속하세요.
"""
import json
import os
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
PAGE = os.path.join(HERE, "todo.html")
PORT = int(os.environ.get("PORT", "8787"))
MAX_BODY = 5 * 1024 * 1024
lock = threading.Lock()


def read_store():
    try:
        with open(DATA, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"rev": 0, "data": None}


def write_store(obj):
    if os.path.exists(DATA):
        shutil.copy2(DATA, DATA + ".bak")  # 직전 상태를 백업으로 남김
    fd, tmp = tempfile.mkstemp(dir=HERE, prefix=".data-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, DATA)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/todo.html"):
            with open(PAGE, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/api/data":
            with lock:
                self._send(200, read_store())
        else:
            self._send(404, {"error": "not found"})

    def do_PUT(self):
        if self.path.split("?")[0] != "/api/data":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0 or n > MAX_BODY:
                raise ValueError("size")
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            base, data = body["rev"], body["data"]
            if not isinstance(data, dict):
                raise ValueError("data")
        except Exception:
            return self._send(400, {"error": "bad request"})
        with lock:
            cur = read_store()
            if base != cur["rev"]:
                return self._send(409, cur)  # 다른 기기가 먼저 저장함
            new = {"rev": cur["rev"] + 1, "data": data}
            write_store(new)
            self._send(200, {"rev": new["rev"]})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"할 일 서버 실행 중: http://127.0.0.1:{PORT}  (데이터: {DATA})", flush=True)
    srv.serve_forever()
