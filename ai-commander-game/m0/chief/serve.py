"""參謀長服務（施工單 16，ADR-0015 D23）：本機 HTTP JSON，標準庫 http.server，不加依賴。

    uv run chief serve --port 8765 --provider fake [--token <亂數>]
    POST /session/start {board, provider?, model?, harness?, doctrine?, lang?, budget_usd?, effort?, aar_provider?, aar_model?} → 會話資訊與開局引用句
    POST /tick {t, board}            → 命令（已過驗證器）、退回、用量、費用、推翻後果
    POST /override {unit_id, player_order, ai_order?, board?}
    POST /battle/end {board, result} → 戰報卡
    POST /aar/line | /aar/discuss {text|index} | /aar/propose | /aar/adopt | /aar/skip | /aar/undo
    GET  /status | /health ；POST /settings {...} ；POST /shutdown
請求序列化（一把鎖）；--idle-exit 秒內沒請求就自動退出（處理中的請求不算閒置）。
只綁 127.0.0.1；給 --token 時每個請求（除 GET /health）要帶 X-Chief-Token，否則 401。金鑰在 .env，從不經過 HTTP。
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from .board import BoardError
from .bridge import ChiefSession, ConflictError, SessionConfig

__version__ = "0.2"
START_FIELDS = ("provider", "model", "harness", "doctrine", "lang", "budget_usd", "effort", "aar_provider", "aar_model")   # §16：/session/start 只收這些
MAX_BODY = 16 * 1024 * 1024


def _looks_like_board(body: dict) -> bool:
    return "board" not in body and isinstance(body.get("orbat"), list) and "schema_version" in body


class ChiefService:
    """一個服務、一個目前會話。"""

    def __init__(self, defaults: SessionConfig, token: Optional[str] = None) -> None:
        self.defaults = defaults
        self.token = token or None
        self.session: Optional[ChiefSession] = None
        self.lock = threading.Lock()
        self._count_lock = threading.Lock()
        self.last_request = time.time()
        self.requests = 0
        self.in_flight = 0

    # 閒置計時：請求開始與結束都算「有活動」，處理中的請求不會被閒置退出殺掉
    def begin(self) -> None:
        with self._count_lock:
            self.in_flight += 1
            self.requests += 1
            self.last_request = time.time()

    def finish(self) -> None:
        with self._count_lock:
            self.in_flight -= 1
            self.last_request = time.time()

    def idle_for(self) -> float:
        with self._count_lock:
            return -1.0 if self.in_flight > 0 else time.time() - self.last_request

    def start(self, body: dict) -> dict:
        if _looks_like_board(body):          # 驗收腳本直接 -d @board.json 也通
            body = {"board": body}
        board = body.get("board")
        if not isinstance(board, dict):
            raise BoardError("缺少 board（Board v0.2 物件）")
        overrides = {k: v for k, v in body.items() if k in START_FIELDS and v is not None}
        if "doctrine" in overrides:          # 準則檔只能在工作目錄（m0/）底下：別讓任何本機程式把系統檔餵進 LLM
            from .harness import _inside
            overrides["doctrine"] = str(_inside(Path.cwd(), str(overrides["doctrine"])))
        cfg = SessionConfig(**{**asdict(self.defaults), **overrides})
        new = ChiefSession(cfg, board)
        if self.session is not None:
            self.session.close()             # 上一場沒走完戰後流程 → 戰例補進戰例庫
        self.session = new
        return self.session.info()

    def close(self) -> None:
        if self.session is not None:
            self.session.close()

    def require(self) -> ChiefSession:
        if self.session is None:
            raise BoardError("還沒有會話（先 POST /session/start）")
        return self.session

    def handle(self, method: str, path: str, body: dict, token: Optional[str] = None) -> tuple[int, dict]:
        if method == "GET" and path == "/health":
            return 200, {"ok": True, "version": __version__, "session": self.session is not None, "requests": self.requests, "auth": bool(self.token)}
        if self.token and token != self.token:
            return 401, {"error": "缺少或錯誤的 X-Chief-Token"}
        if method == "GET":
            if path == "/status":
                return 200, (self.session.status() if self.session else {"session": False})
            return 404, {"error": f"沒有這個端點：GET {path}（GET 只有 /health、/status）"}
        if method != "POST":
            return 405, {"error": "只接受 GET 與 POST"}
        if path == "/session/start":
            return 200, self.start(body)
        if path == "/shutdown":
            return 200, {"bye": True}
        if path == "/settings":
            return 200, self.require().settings(**{k: body.get(k) for k in ("provider", "model", "lang", "budget_usd", "effort", "aar_provider", "aar_model")})
        if path == "/health":
            return 405, {"error": "/health 只接受 GET"}
        s = self.require()
        if path == "/tick":
            if not isinstance(body.get("board"), dict):
                raise BoardError("缺少 board")
            return 200, s.tick(body["board"], body.get("t"))
        if path == "/override":
            if not body.get("unit_id") or not isinstance(body.get("player_order"), dict):
                raise BoardError("缺少 unit_id 或 player_order")
            return 200, s.override(str(body["unit_id"]), body["player_order"], body.get("board"), body.get("ai_order"))
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
        return 404, {"error": f"沒有這個端點：{path}"}


def make_handler(service: ChiefService, server_ref: dict):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, payload: dict, close: bool = False) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                if close:                      # 連線上可能殘留沒讀完的 body：告訴客戶端這條線不要重用
                    self.send_header("Connection", "close")
                    self.close_connection = True
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True   # 客戶端已經走了；服務不用噴 traceback

        def _read_body(self) -> Optional[dict]:
            """回 dict；回 None 表示已送出錯誤回應。"""
            if self.headers.get("Transfer-Encoding"):
                self._send(411, {"error": "請帶 Content-Length（不支援 chunked）"}, close=True)
                return None
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._send(400, {"error": "Content-Length 不是數字"}, close=True)
                return None
            if n < 0 or n > MAX_BODY:
                self._send(413, {"error": f"請求太大（上限 {MAX_BODY // (1024 * 1024)} MiB）"}, close=True)
                return None
            raw = self.rfile.read(n) if n else b""
            if not raw:
                return {}
            try:
                body = json.loads(raw.decode("utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError) as err:
                self._send(400, {"error": f"請求不是合法的 JSON：{err}"})
                return None
            if not isinstance(body, dict):
                self._send(400, {"error": "請求必須是 JSON 物件"})
                return None
            return body

        def _dispatch(self, method: str) -> None:
            body: Optional[dict] = {}
            if method == "POST":
                body = self._read_body()
                if body is None:
                    return
            path = self.path.split("?", 1)[0]
            service.begin()
            try:
                with service.lock:
                    code, payload = service.handle(method, path, body, self.headers.get("X-Chief-Token"))
            except ConflictError as err:
                code, payload = 409, {"error": str(err)}
            except BoardError as err:
                code, payload = 400, {"error": str(err)}
            except (ValueError, KeyError, TypeError, NotImplementedError) as err:
                code, payload = 400, {"error": f"{type(err).__name__}: {err}"}
            except Exception as err:  # noqa: BLE001 - 服務不能因為一次失敗就死掉
                code, payload = 500, {"error": f"服務內部錯誤：{type(err).__name__}: {str(err)[:300]}"}
            finally:
                service.finish()
            self._send(code, payload)
            if code == 200 and path == "/shutdown" and server_ref.get("server") is not None:
                threading.Thread(target=server_ref["server"].shutdown, daemon=True).start()

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def _not_allowed(self) -> None:
            try:                               # 把 body 讀掉，殘餘位元組才不會毒化下一個 keep-alive 請求
                n = int(self.headers.get("Content-Length") or 0)
                if 0 < n <= MAX_BODY:
                    self.rfile.read(n)
                    n = 0
            except ValueError:
                n = -1
            self._send(405, {"error": "只接受 GET 與 POST"}, close=n != 0 or bool(self.headers.get("Transfer-Encoding")))

        do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _not_allowed   # noqa: N815

        def log_message(self, fmt: str, *args: Any) -> None:  # 安靜；需要時用 --verbose
            if server_ref.get("verbose"):
                super().log_message(fmt, *args)
    return Handler


def run_server(defaults: SessionConfig, host: str = "127.0.0.1", port: int = 8765, idle_exit_s: float = 600.0,
               verbose: bool = False, ready_cb=None, token: Optional[str] = None) -> int:
    service = ChiefService(defaults, token=token)
    ref: dict = {"verbose": verbose}
    server = ThreadingHTTPServer((host, port), make_handler(service, ref))
    server.daemon_threads = True
    ref["server"] = server
    actual = server.server_address[1]
    print(f"參謀長服務 http://{host}:{actual}（{defaults.provider}/{defaults.model or '預設模型'}；{idle_exit_s:.0f} 秒沒請求自動退出"
          + ("；需 X-Chief-Token" if token else "") + "）", flush=True)
    if ready_cb:
        ready_cb(actual)

    poll = min(5.0, max(0.5, idle_exit_s / 2)) if idle_exit_s > 0 else 5.0

    def idle_watch() -> None:
        while True:
            time.sleep(poll)
            if idle_exit_s > 0 and service.idle_for() > idle_exit_s:
                print("參謀長服務閒置太久，退出。", flush=True)
                server.shutdown()
                return
    threading.Thread(target=idle_watch, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    service.close()
    return 0
