"""參謀長服務（施工單 16，ADR-0015 D23）：本機 HTTP JSON，標準庫 http.server，不加依賴。

    uv run chief serve --port 8765 --provider fake
    POST /session/start {board, provider?, model?, harness?, doctrine?, lang?, budget_usd?, effort?} → 會話資訊與開局引用句
    POST /tick {t, board}            → 命令（已過驗證器）、退回、用量、費用、推翻後果
    POST /override {unit_id, player_order, ai_order?, board?}
    POST /battle/end {board, result} → 戰報卡
    POST /aar/line | /aar/discuss {text|index} | /aar/propose | /aar/adopt | /aar/skip | /aar/undo
    GET  /status | /health ；POST /settings {...} ；POST /shutdown
請求序列化（一把鎖）；--idle-exit 秒內沒請求就自動退出。金鑰在 .env，從不經過 HTTP。
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from .board import BoardError
from .bridge import ChiefSession, SessionConfig

__version__ = "0.1"


class ChiefService:
    """一個服務、一個目前會話。"""

    def __init__(self, defaults: SessionConfig) -> None:
        self.defaults = defaults
        self.session: Optional[ChiefSession] = None
        self.lock = threading.Lock()
        self.last_request = time.time()
        self.requests = 0

    def start(self, body: dict) -> dict:
        cfg = SessionConfig(**{**asdict(self.defaults), **{k: v for k, v in body.items() if k in SessionConfig.__dataclass_fields__ and v is not None}})
        board = body.get("board")
        if not isinstance(board, dict):
            raise BoardError("缺少 board（Board v0.2 物件）")
        self.session = ChiefSession(cfg, board)
        return self.session.info()

    def require(self) -> ChiefSession:
        if self.session is None:
            raise BoardError("還沒有會話（先 POST /session/start）")
        return self.session

    def handle(self, method: str, path: str, body: dict) -> tuple[int, dict]:
        self.requests += 1
        self.last_request = time.time()
        if method == "GET" and path == "/health":
            return 200, {"ok": True, "version": __version__, "session": self.session is not None, "requests": self.requests}
        if method == "GET" and path == "/status":
            return 200, (self.require().status() if self.session else {"session": False})
        if method != "POST":
            return 405, {"error": "只接受 GET /health、/status 與 POST"}
        if path == "/session/start":
            return 200, self.start(body)
        if path == "/shutdown":
            return 200, {"bye": True}
        s = self.require()
        if path == "/tick":
            if not isinstance(body.get("board"), dict):
                raise BoardError("缺少 board")
            return 200, s.tick(body["board"], body.get("t"))
        if path == "/override":
            if not body.get("unit_id") or not isinstance(body.get("player_order"), dict):
                raise BoardError("缺少 unit_id 或 player_order")
            return 200, s.override(body["unit_id"], body["player_order"], body.get("board"), body.get("ai_order"))
        if path == "/battle/end":
            if not isinstance(body.get("board"), dict) or not isinstance(body.get("result"), dict):
                raise BoardError("缺少 board 或 result")
            return 200, s.end(body["board"], body["result"])
        if path == "/aar/line":
            return 200, s.aar_line()
        if path == "/aar/discuss":
            return 200, s.discuss(body.get("text"), body.get("index"))
        if path == "/aar/propose":
            return 200, s.propose()
        if path == "/aar/adopt":
            return 200, s.adopt()
        if path == "/aar/skip":
            return 200, s.skip()
        if path == "/aar/undo":
            return 200, s.undo()
        if path == "/settings":
            return 200, s.settings(**{k: body.get(k) for k in ("provider", "model", "lang", "budget_usd", "effort", "aar_provider", "aar_model")})
        return 404, {"error": f"沒有這個端點：{path}"}


def make_handler(service: ChiefService, server_ref: dict):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _dispatch(self, method: str) -> None:
            body: dict = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                if raw:
                    try:
                        body = json.loads(raw.decode("utf-8-sig"))
                    except (json.JSONDecodeError, UnicodeDecodeError) as err:
                        self._send(400, {"error": f"請求不是合法的 JSON：{err}"})
                        return
                    if not isinstance(body, dict):
                        self._send(400, {"error": "請求必須是 JSON 物件"})
                        return
            path = self.path.split("?", 1)[0]
            try:
                with service.lock:
                    code, payload = service.handle(method, path, body)
            except BoardError as err:
                code, payload = 400, {"error": str(err)}
            except (ValueError, KeyError, TypeError, NotImplementedError) as err:
                code, payload = 400, {"error": f"{type(err).__name__}: {err}"}
            except Exception as err:  # noqa: BLE001 - 服務不能因為一次失敗就死掉
                code, payload = 500, {"error": f"服務內部錯誤：{type(err).__name__}: {str(err)[:300]}"}
            self._send(code, payload)
            if path == "/shutdown" and server_ref.get("server") is not None:
                threading.Thread(target=server_ref["server"].shutdown, daemon=True).start()

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def log_message(self, fmt: str, *args: Any) -> None:  # 安靜；需要時用 --verbose
            if server_ref.get("verbose"):
                super().log_message(fmt, *args)
    return Handler


def run_server(defaults: SessionConfig, host: str = "127.0.0.1", port: int = 8765, idle_exit_s: float = 600.0,
               verbose: bool = False, ready_cb=None) -> int:
    service = ChiefService(defaults)
    ref: dict = {"verbose": verbose}
    server = ThreadingHTTPServer((host, port), make_handler(service, ref))
    server.daemon_threads = True
    ref["server"] = server
    actual = server.server_address[1]
    print(f"參謀長服務 http://{host}:{actual}（{defaults.provider}/{defaults.model or '預設模型'}；{idle_exit_s:.0f} 秒沒請求自動退出）", flush=True)
    if ready_cb:
        ready_cb(actual)

    def idle_watch() -> None:
        while True:
            time.sleep(5.0)
            if idle_exit_s > 0 and time.time() - service.last_request > idle_exit_s:
                print("參謀長服務閒置太久，退出。", flush=True)
                server.shutdown()
                return
    threading.Thread(target=idle_watch, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    return 0
