"""參謀長服務（施工單 16，ADR-0015 D23）：本機 HTTP JSON，標準庫 http.server，不加依賴。

    uv run chief serve --port 8765 --provider fake [--token <亂數>]
    POST /session/start {board, provider?, model?, harness?, doctrine?, lang?, budget_usd?, effort?, aar_provider?, aar_model?} → 會話資訊與開局引用句
    POST /tick {t, board}            → 命令（已過驗證器）、退回、用量、費用、推翻後果
    POST /override {unit_id, player_order, t?, ai_order?, board?} ；POST /release {unit_ids}
    POST /battle/end {board, result} → 戰報卡
    POST /aar/line | /aar/discuss {text|index} | /aar/propose | /aar/adopt | /aar/skip | /aar/undo
    GET  /status | /health ；POST /settings {...} ；POST /shutdown
請求序列化（一把鎖）；--idle-exit 秒內沒請求就自動退出（處理中的請求不算閒置）。
只綁 127.0.0.1；給 --token 時每個請求（除 GET /health）要帶 X-Chief-Token，否則 401。金鑰在 .env，從不經過 HTTP。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

from .board import BoardError
from .bridge import ChiefSession, ConflictError, SessionConfig, _validation_text

__version__ = "0.2"
START_FIELDS = ("provider", "model", "harness", "doctrine", "lang", "budget_usd", "effort", "aar_provider", "aar_model")   # §16：/session/start 只收這些
MAX_BODY = 16 * 1024 * 1024
Lang = Literal["zh-TW", "zh-CN", "en"]
Effort = Literal["low", "medium", "high"]


class StartFields(BaseModel):
    """`/session/start` 的設定欄位：只收白名單、驗型別（壞型別若放進會話，之後每拍都 TypeError）。"""
    model_config = ConfigDict(extra="ignore", strict=True)   # "0.5" 這種字串也擋：引擎送的就該是數字
    provider: Optional[str] = None
    model: Optional[str] = None
    harness: Optional[str] = None
    doctrine: Optional[str] = None
    lang: Optional[Lang] = None
    budget_usd: Optional[float] = None
    effort: Optional[Effort] = None
    aar_provider: Optional[str] = None
    aar_model: Optional[str] = None


class SettingsFields(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)   # "0.5" 這種字串也擋：引擎送的就該是數字
    provider: Optional[str] = None
    model: Optional[str] = None
    lang: Optional[Lang] = None
    budget_usd: Optional[float] = None
    effort: Optional[Effort] = None
    aar_provider: Optional[str] = None
    aar_model: Optional[str] = None


def _fields(model: type[BaseModel], body: dict, what: str) -> dict:
    try:
        return {k: v for k, v in model.model_validate(body).model_dump().items() if v is not None}
    except ValidationError as err:
        raise BoardError(f"{what} 不合法：{_validation_text(err)}") from None


def pid_alive(pid: int) -> bool:
    """父程序還在嗎？Windows 不能用 os.kill(pid, 0)（那會 TerminateProcess），用 OpenProcess + GetExitCodeProcess。"""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32   # type: ignore[attr-defined]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259   # STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:                                   # Linux：殭屍（父程序還沒 wait 的已結束程序）不算活著
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            state = f.read().rsplit(")", 1)[-1].split()[0]
        return state != "Z"
    except OSError:
        return True


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
        overrides = _fields(StartFields, {k: v for k, v in body.items() if k in START_FIELDS}, "session 設定")
        if "doctrine" in overrides:          # 準則檔只能在工作目錄（m0/）底下：別讓任何本機程式把系統檔餵進 LLM
            from .harness import _inside
            overrides["doctrine"] = str(_inside(Path.cwd(), str(overrides["doctrine"])))
        if "harness" in overrides:           # 參謀長包只能用名字（harness/<name>/），不能是路徑
            from .harness import NAME_RE
            h = str(overrides["harness"])
            if h not in ("", "none", "-", "off") and not NAME_RE.match(h):
                raise BoardError(f"參謀長包名稱不合法：「{h}」（只能是 harness/ 底下的名字，或 none）")
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
            return 200, self.require().settings(**_fields(SettingsFields, body, "settings"))
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
            if body.get("ai_order") is not None and not isinstance(body["ai_order"], dict):
                raise BoardError("ai_order 要是物件（{task, target}）")
            return 200, s.override(str(body["unit_id"]), body["player_order"], body.get("board"), body.get("ai_order"), body.get("t"))
        if path == "/release":
            ids = body.get("unit_ids")
            if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
                raise BoardError("缺少 unit_ids（字串清單）")
            return 200, s.release(ids)
        if path == "/battle/end":
            if not isinstance(body.get("board"), dict) or not isinstance(body.get("result"), dict):
                raise BoardError("缺少 board 或 result")
            return 200, s.end(body["board"], body["result"])
        if path == "/aar/line":
            return 200, s.aar_line()
        if path == "/aar/discuss":
            index = body.get("index")
            if index is not None and (isinstance(index, bool) or not isinstance(index, (int, float)) or int(index) != index):
                raise BoardError("index 要是 1～3 的整數")
            return 200, s.discuss(body.get("text"), None if index is None else int(index))
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

        def _drain(self) -> bool:
            """非 POST 卻帶 body：讀掉，殘餘位元組才不會毒化同一條連線的下一個請求。回傳是否該關連線。"""
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return True
            if n < 0 or n > MAX_BODY or self.headers.get("Transfer-Encoding"):
                return True
            if n:
                self.rfile.read(n)
            return False

        def _dispatch(self, method: str) -> None:
            body: Optional[dict] = {}
            if method == "POST":
                body = self._read_body()
                if body is None:
                    return
            elif self._drain():
                self._send(400, {"error": "GET 不該帶 body"}, close=True)
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
            self._send(405, {"error": "只接受 GET 與 POST"}, close=self._drain())

        def do_HEAD(self) -> None:  # noqa: N802 - HEAD 不能有 body：送標頭就關連線
            self._drain()
            self.send_response(405)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _not_allowed   # noqa: N815

        def log_message(self, fmt: str, *args: Any) -> None:  # 安靜；需要時用 --verbose
            if server_ref.get("verbose"):
                super().log_message(fmt, *args)
    return Handler


def run_server(defaults: SessionConfig, host: str = "127.0.0.1", port: int = 8765, idle_exit_s: float = 600.0,
               verbose: bool = False, ready_cb=None, token: Optional[str] = None, parent_pid: Optional[int] = None,
               parent_poll_s: float = 2.0) -> int:
    service = ChiefService(defaults, token=token)
    ref: dict = {"verbose": verbose}
    server = ThreadingHTTPServer((host, port), make_handler(service, ref))
    server.daemon_threads = True
    ref["server"] = server
    actual = server.server_address[1]
    print(f"參謀長服務 http://{host}:{actual}（{defaults.provider}/{defaults.model or '預設模型'}；{idle_exit_s:.0f} 秒沒請求自動退出"
          + ("；需 X-Chief-Token" if token else "") + (f"；父程序 {parent_pid} 消失就退出" if parent_pid else "") + "）", flush=True)
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

    def parent_watch() -> None:   # Godot（或任何啟動者）被殺、被編輯器停止：不靠它來 kill，自己走
        while True:
            time.sleep(parent_poll_s)
            try:
                alive = pid_alive(parent_pid)
            except Exception as err:  # noqa: BLE001 - 查不到就當活著，別讓看門執行緒靜默死掉
                print(f"查父程序 {parent_pid} 失敗（{type(err).__name__}: {err}），當作還活著", flush=True)
                continue
            if not alive:
                print(f"啟動參謀長服務的程序 {parent_pid} 已不在，退出。", flush=True)
                server.shutdown()
                return
    if parent_pid:
        threading.Thread(target=parent_watch, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    service.close()
    return 0
