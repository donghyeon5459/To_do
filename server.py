#!/usr/bin/env python3
"""할 일 앱 서버: todo.html 을 보여주고, 데이터를 data.json 한 파일에 저장합니다.

기본은 127.0.0.1 에서만 열립니다. BIND 를 이 컴퓨터의 Tailscale IP 로 지정하면
같은 Tailscale 네트워크의 기기에서만 접속되고, ALLOWED_LOGINS 로 계정까지 제한할 수 있습니다.
"""
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
PAGE = os.path.join(HERE, "todo.html")
PORT = int(os.environ.get("PORT", "8787"))
MAX_BODY = 5 * 1024 * 1024
# 서버가 열릴 주소. 기본은 이 컴퓨터 안(127.0.0.1)만.
# 다른 기기에서 쓰려면 이 컴퓨터의 Tailscale IP(100.x.x.x)로 지정하세요. 그러면 내 Tailscale 네트워크에서만 접속돼요.
BIND = os.environ.get("BIND", "127.0.0.1")
# 접속을 허용할 Tailscale 계정(쉼표로 구분). 비어 있으면 제한 없음.
ALLOWED = {s.strip() for s in os.environ.get("ALLOWED_LOGINS", "").split(",") if s.strip()}
TS_CLI = os.environ.get("TAILSCALE_CLI", "/Applications/Tailscale.app/Contents/MacOS/Tailscale")
# 이 컴퓨터의 Tailscale 도메인(예: mymac.tailXXXX.ts.net)을 넣으면 https 로 열려요 (브라우저 "주의 요함" 경고 없음).
# Tailscale 이 발급하는 인증서를 쓰고, 만료 전에 자동으로 갱신합니다. 비우면 http.
CERT_DOMAIN = os.environ.get("CERT_DOMAIN", "")
CERT_DIR = os.path.join(HERE, ".certs")
lock = threading.Lock()
_whois = {}  # ip -> (확인한 시각, 계정)


def tailscale_login(ip):
    """접속한 기기 IP가 어느 Tailscale 계정 소유인지 확인 (실패하면 None = 거부)."""
    hit = _whois.get(ip)
    if hit and time.time() - hit[0] < (60 if hit[1] else 5):
        return hit[1]
    login = None
    try:
        # macOS Tailscale 앱의 CLI는 SHLVL 이 없으면 CLI가 아니라 앱 창을 띄우려다 실패함 (자동 실행 환경 대비)
        env = dict(os.environ, SHLVL="1")
        out = subprocess.run([TS_CLI, "whois", "--json", ip], capture_output=True, timeout=5, env=env)
        login = json.loads(out.stdout)["UserProfile"]["LoginName"]
    except Exception:
        pass
    _whois[ip] = (time.time(), login)
    return login


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


def fetch_cert():
    """Tailscale 에서 https 인증서를 받아 .certs/ 에 저장. (성공 여부, 인증서 경로, 키 경로)"""
    os.makedirs(CERT_DIR, mode=0o700, exist_ok=True)
    crt, key = os.path.join(CERT_DIR, "server.crt"), os.path.join(CERT_DIR, "server.key")
    try:
        r = subprocess.run([TS_CLI, "cert", "--cert-file", crt, "--key-file", key, CERT_DOMAIN],
                           capture_output=True, timeout=90, env=dict(os.environ, SHLVL="1"))
        return r.returncode == 0, crt, key
    except Exception:
        return False, crt, key


def refresh_cert_loop(ctx):
    while True:
        time.sleep(12 * 3600)
        ok, crt, key = fetch_cert()
        if ok:
            ctx.load_cert_chain(crt, key)  # 새로 들어오는 접속부터 새 인증서 사용


class Server(ThreadingHTTPServer):
    ctx = None

    def process_request_thread(self, request, client_address):
        # 접속별 스레드에서 처리하므로 느린 접속이 다른 접속을 막지 않음
        raw, conn = request, request
        try:
            if self.ctx:
                conn = self._tls_or_redirect(raw)
            if conn is not None:
                self.finish_request(conn, client_address)
        except Exception:
            self.handle_error(raw, client_address)
        finally:
            self.shutdown_request(conn if conn is not None else raw)

    def _tls_or_redirect(self, raw):
        """https 접속이면 암호화 연결을 열고, 예전 http 주소로 들어온 접속은 https 주소로 안내(301)."""
        raw.settimeout(Handler.timeout)
        first = raw.recv(1, socket.MSG_PEEK)
        if not first:
            return None
        if first[0] == 0x16:  # TLS 시작 바이트
            return self.ctx.wrap_socket(raw, server_side=True)
        try:
            path = raw.recv(4096).split(b" ", 2)[1].decode("ascii")
        except Exception:
            path = "/"
        if not path.startswith("/") or any(c in path for c in " \r\n"):
            path = "/"
        raw.sendall(("HTTP/1.1 301 Moved Permanently\r\nLocation: https://%s:%d%s\r\n"
                     "Content-Length: 0\r\nConnection: close\r\n\r\n" % (CERT_DOMAIN, PORT, path)).encode("ascii"))
        return None

    def handle_error(self, request, client_address):  # https 에 http 로 접속하는 등의 오류를 한 줄로만 기록
        print(f"연결 오류 {client_address[0]}: {sys.exc_info()[1]}", file=sys.stderr, flush=True)


class Handler(BaseHTTPRequestHandler):
    timeout = 60

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _allowed(self):
        if not ALLOWED:
            return True
        remote = self.client_address[0]
        if remote not in ("127.0.0.1", "::1"):
            return tailscale_login(remote) in ALLOWED      # Tailscale 로 들어온 다른 기기
        login = self.headers.get("Tailscale-User-Login")   # `tailscale serve` 를 거쳐 온 경우
        if login:
            return login in ALLOWED
        # 헤더 없이 127.0.0.1 로 직접 연 경우(이 컴퓨터에서 직접)만 허용
        return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

    def _deny(self):
        ip = self.client_address[0]
        who = self.headers.get("Tailscale-User-Login") or _whois.get(ip, (0, None))[1]
        print(f"접속 거부 {ip} (계정: {who})", file=sys.stderr, flush=True)
        self._send(403, {"error": "forbidden"})

    def do_GET(self):
        if not self._allowed():
            return self._deny()
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
        if not self._allowed():
            return self._deny()
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
    srv = Server((BIND, PORT), Handler)
    if CERT_DOMAIN:
        ok, crt, key = fetch_cert()
        if not ok:  # http 로 조용히 넘어가지 않고 종료 → 자동 실행이 곧 다시 시도함
            print("Tailscale 인증서를 받지 못했어요. Tailscale 이 켜져 있고 HTTPS 인증서가 허용돼 있는지 확인하세요.", file=sys.stderr, flush=True)
            sys.exit(1)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(crt, key)
        srv.ctx = ctx
        threading.Thread(target=refresh_cert_loop, args=(ctx,), daemon=True).start()
        url = f"https://{CERT_DOMAIN}:{PORT}"
    else:
        url = f"http://{BIND}:{PORT}"
    print(f"할 일 서버 실행 중: {url}  (데이터: {DATA})", flush=True)
    srv.serve_forever()
