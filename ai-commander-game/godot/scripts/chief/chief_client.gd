class_name ChiefClient
extends Node
## 參謀長客戶端（施工單 17，ADR-0015 D23／D25）：啟動本機 Python 服務 `uv run chief serve`、健康檢查、
## 請求一次一個（HTTPRequest 本來就只能一個在飛；多個呼叫者排隊）、逾時、關機。
## 金鑰在 m0/.env，Godot 從不碰；--token 由這裡產生亂數帶給服務並放在 X-Chief-Token（docs/10 §16）。

signal online_changed(online: bool)
signal busy_changed(busy: bool)
signal replied(path: String, code: int, body: Dictionary, latency_s: float)
signal _slot_free

const HEALTH_TIMEOUT_S := 10.0
const COLD_BOOT_TIMEOUT_S := 45.0    # 自己啟動且子程序還活著：第一次 uv run 要建環境，可以等久一點
const DEFAULT_TIMEOUT_S := 60.0      # 施工單 17：60 秒無回覆算無回應
const IDLE_EXIT_S := 600             # 服務多久沒請求自滅：戰後 AAR 畫面玩家可能看很久，客戶端死了由 --parent-pid 收掉，這裡只是保險
const RESULT_TEXT := {
	HTTPRequest.RESULT_CANT_CONNECT: "連不上參謀長服務", HTTPRequest.RESULT_CANT_RESOLVE: "解析不了位址",
	HTTPRequest.RESULT_CONNECTION_ERROR: "連線中斷", HTTPRequest.RESULT_TIMEOUT: "逾時沒有回覆",
	HTTPRequest.RESULT_NO_RESPONSE: "服務沒有回應", HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED: "回應太大",
	HTTPRequest.RESULT_REQUEST_FAILED: "請求失敗", RESULT_CANCELLED: "請求已取消（關機中）",
}
const RESULT_CANCELLED := -1		  # HTTPRequest 沒有「取消」這個結果碼；stop() 取消在飛請求時自己補發這個

var base_url := ""
var token := ""
var pid := -1                         # 自己啟動的服務子程序；<=0 表示沒有（連到別人起的）
var online := false
var busy := false                     # 有請求在飛（HUD「參謀長思考中」）
var busy_since_msec := 0
var last_error := ""
var requests := 0
var _http: HTTPRequest
var _taken := false
var _stopping := false               # stop() 進行中：排隊的與新的請求（除 /shutdown）直接回「已取消」

func _ready() -> void:
	_http = HTTPRequest.new()
	_http.name = "HTTP"
	_http.accept_gzip = false
	add_child(_http)

## 找一個目前空著的本機埠（服務綁 127.0.0.1）。
static func free_port() -> int:
	var srv := TCPServer.new()
	if srv.listen(0, "127.0.0.1") != OK:
		return 8765
	var p := srv.get_local_port()
	srv.stop()
	return p

static func new_token() -> String:
	return Crypto.new().generate_random_bytes(16).hex_encode()

## 啟動服務子程序：`uv run --directory <m0> chief serve --port <p> --provider <provider> --token <亂數>
##   --parent-pid <Godot 的 pid> --idle-exit 90 <extra>`。
## uv 是外殼、Python 是它的子程序：OS.kill 只殺得到 uv，所以服務自己看 --parent-pid（Godot 消失 2 秒內退出）、
## 加 --idle-exit 當保險；extra 在後面可覆寫。回傳 pid（<=0＝啟動失敗；Unix 下 exec 失敗仍回 pid>0，
## 由 wait_online 的「一啟動就結束」偵測）。之後要 wait_online() 等 /health 通。
func launch(provider: String, extra_args: PackedStringArray = PackedStringArray(), uv_path: String = "uv", port: int = 0) -> int:
	var p := port if port > 0 else free_port()
	token = new_token()
	var args := PackedStringArray(["run", "--directory", BoardIO.m0_dir(), "chief", "serve", "--port", str(p), "--provider", provider, "--token", token,
		"--parent-pid", str(OS.get_process_id()), "--idle-exit", str(IDLE_EXIT_S)])
	args.append_array(extra_args)
	base_url = "http://127.0.0.1:%d" % p
	pid = OS.create_process(uv_path, args, false)
	if pid <= 0:
		last_error = "啟動不了參謀長服務（找不到 %s？）" % uv_path
		pid = -1
	return pid

## 連到已經在跑的服務（測試、或老闆自己開了一個 chief serve）。
func connect_to(url: String, token_: String = "") -> void:
	base_url = url.rstrip("/")
	token = token_
	pid = -1

## 等 /health 通（每 0.5 秒問一次）。連別人的服務最多 timeout_s 秒；自己啟動且子程序還活著則放寬到 cold_timeout_s
## （第一次 uv run 要建 .venv，常超過 10 秒）。
func wait_online(timeout_s: float = HEALTH_TIMEOUT_S, cold_timeout_s: float = COLD_BOOT_TIMEOUT_S) -> bool:
	var t0 := Time.get_ticks_msec()
	while true:
		var r: Dictionary = await call_api("GET", "/health", {}, 2.0)
		if r["code"] == 200:
			_set_online(true)
			return true
		var waited := float(Time.get_ticks_msec() - t0) / 1000.0
		if _stopping:
			last_error = "啟動被中止（關機）"
			break
		if pid > 0 and not OS.is_process_running(pid):
			last_error = "參謀長服務一啟動就結束了（找不到 uv？或 m0 的 Python 環境有問題：先在 m0 跑 uv sync）"
			break
		var limit := cold_timeout_s if (pid > 0 and cold_timeout_s > timeout_s) else timeout_s
		if waited >= limit:
			last_error = "參謀長服務 %d 秒內沒起來（/health 不通）" % int(limit)
			break
		await get_tree().create_timer(0.5).timeout
	_set_online(false)
	return false

## 送一個請求，等回覆。回 {code, body, error, latency_s, path}；送不出／逾時／連不上時 code=0、error 是人話。
## 服務回 4xx／5xx 時 code 照回、error＝服務的人話。
func call_api(method: String, path: String, body: Dictionary = {}, timeout_s: float = DEFAULT_TIMEOUT_S) -> Dictionary:
	var cancelled := {"code": 0, "body": {}, "error": str(RESULT_TEXT[RESULT_CANCELLED]), "latency_s": 0.0, "path": path}
	if _stopping and path != "/shutdown":
		return cancelled
	while _taken:
		await _slot_free
		if _stopping and path != "/shutdown":   # 排隊期間開始關機：不要再送出去
			return cancelled
	_taken = true
	_set_busy(true)
	requests += 1
	var out := {"code": 0, "body": {}, "error": "", "latency_s": 0.0, "path": path}
	var headers := PackedStringArray(["Content-Type: application/json", "Accept: application/json"])
	if token != "":
		headers.append("X-Chief-Token: " + token)
	_http.timeout = timeout_s
	var t0 := Time.get_ticks_msec()
	var m := HTTPClient.METHOD_GET if method == "GET" else HTTPClient.METHOD_POST
	var err := _http.request(base_url + path, headers, m, "" if method == "GET" else JSON.stringify(body))
	if err != OK:
		out["error"] = "送不出請求：%s" % error_string(err)
	else:
		var res: Array = await _http.request_completed
		out["latency_s"] = float(Time.get_ticks_msec() - t0) / 1000.0
		var result: int = res[0]
		if result != HTTPRequest.RESULT_SUCCESS:
			out["error"] = str(RESULT_TEXT.get(result, "HTTP 失敗（%d）" % result))
		else:
			out["code"] = int(res[1])
			var parsed: Variant = JSON.parse_string((res[3] as PackedByteArray).get_string_from_utf8())
			out["body"] = parsed if parsed is Dictionary else {}
			if out["code"] >= 400:
				out["error"] = str(out["body"].get("error", "HTTP %d" % out["code"]))
	if out["code"] == 0 and path != "/health":
		last_error = out["error"]
	_taken = false
	_set_busy(false)
	_slot_free.emit()
	# 延後發：先讓 await call_api 的呼叫者（例如 _chief_tick 的 mark_done）跑完，監聽 replied 的人才接手
	call_deferred("emit_signal", "replied", path, out["code"], out["body"], out["latency_s"])
	return out

## 幾秒前開始等回覆（沒有在飛就 0）。
func busy_seconds() -> float:
	return float(Time.get_ticks_msec() - busy_since_msec) / 1000.0 if busy else 0.0

# ---- 端點包裝（docs/10 §16）----
func start_session(board: Dictionary, settings: Dictionary = {}) -> Dictionary:
	var body := settings.duplicate()
	body["board"] = board
	return await call_api("POST", "/session/start", body, 30.0)

func tick(t: float, board: Dictionary) -> Dictionary:
	return await call_api("POST", "/tick", {"t": t, "board": board}, DEFAULT_TIMEOUT_S)

func override(unit_id: String, player_order: Dictionary, board: Dictionary, t: float = -1.0, ai_order: Variant = null) -> Dictionary:
	var body := {"unit_id": unit_id, "player_order": player_order, "board": board}
	if t >= 0.0:
		body["t"] = t
	if ai_order != null:
		body["ai_order"] = ai_order
	return await call_api("POST", "/override", body, 10.0)

func battle_end(board: Dictionary, result: Dictionary) -> Dictionary:
	return await call_api("POST", "/battle/end", {"board": board, "result": result}, 30.0)

func status() -> Dictionary:
	return await call_api("GET", "/status", {}, 5.0)

## 關機：在飛的請求先取消（不然 /shutdown 會排在一個最長 60 秒的 /tick 後面），再請服務自己退（/shutdown，
## 會補寫戰例），2 秒內沒結束就 kill。
func stop() -> void:
	_stopping = true
	var guard := 0
	while _taken and guard < 8:
		_http.cancel_request()
		# cancel_request 不會發 request_completed：自己補一個「已取消」，讓等在 call_api 裡的人立刻拿到結果；
		# 排隊中的會在醒來時看到 _stopping 自己退出
		_http.request_completed.emit(RESULT_CANCELLED, 0, PackedStringArray(), PackedByteArray())
		guard += 1
	if base_url != "" and online:
		await call_api("POST", "/shutdown", {}, 3.0)
	if pid > 0:
		var deadline := Time.get_ticks_msec() + 2000
		while OS.is_process_running(pid) and Time.get_ticks_msec() < deadline:
			await get_tree().create_timer(0.1).timeout
		if OS.is_process_running(pid):
			OS.kill(pid)
		pid = -1
	_set_online(false)
	_stopping = false

## 節點被拆掉（場景重載）而沒先 stop()：直接 kill，別留孤兒程序。
func _exit_tree() -> void:
	if pid > 0 and OS.is_process_running(pid):
		OS.kill(pid)
		pid = -1

func _set_online(v: bool) -> void:
	if v != online:
		online = v
		online_changed.emit(v)

func _set_busy(v: bool) -> void:
	if v != busy:
		busy = v
		busy_since_msec = Time.get_ticks_msec() if v else 0
		busy_changed.emit(v)
