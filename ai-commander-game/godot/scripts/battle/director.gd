class_name Director
extends RefCounted
## 導演（施工單 14）：一場 5 分鐘會戰的開局、劇本排程、天氣變化、結束判定、結果與快照。
##
## 劇本沿用 M0 格式（orders 以回合為鍵；weather_changes／time_changes 同），第 n 回合的命令在第 (n−1)×30 秒下達。
## 結束（§7）：300 秒到，或一方總戰力 < 初始的 30%。勝負＝據點分，再比剩餘戰力。
## 快照：每 30 秒把戰情板寫到 out_dir/t<n>.json（t0 為開局），M0 的 chief replay 能回放。

const TURN_SECONDS := 30.0
const MAX_TURNS := 10
const END_STRENGTH_RATIO := 0.30
const DIFFICULTY_SCRIPTS := {"easy": "m0://samples/enemy_v1_easy.json", "normal": "m0://samples/enemy_script_v1.json", "hard": "m0://samples/enemy_v1_hard.json"}

var orbat: Orbat
var writer: BoardWriter
var friendly := {}            # 我方劇本（可空：M2 前由空白鍵／參謀長下令）
var enemy := {}               # 敵方劇本
var difficulty := "normal"
var out_dir := ""             # 快照資料夾（"" 不寫）
var initial := {"us": 0.0, "enemy": 0.0}
var next_turn := 1            # 下一個要下令的回合
var finished := false
var end_reason := ""          # turns / strength
var result := {}
var snapshots := 0

func _init(orbat_: Orbat, writer_: BoardWriter, friendly_: Dictionary, enemy_: Dictionary, difficulty_: String = "normal", out_dir_: String = "") -> void:
	orbat = orbat_
	writer = writer_
	friendly = friendly_
	enemy = enemy_
	difficulty = difficulty_
	out_dir = out_dir_
	initial["us"] = orbat.total_strength("us")
	initial["enemy"] = orbat.total_strength("enemy")
	orbat.second_hooks.append(_on_second)   # 依賴順序：BoardWriter.update 先掛，_on_second 後掛（快照時歸屬與敵情已是當秒的）
	_clear_out_dir()
	_snapshot(0)

## 已知的難度才算；其他一律當 normal 並警告（M0 的 CLI 是直接拒收）。
static func normalize_difficulty(d: String) -> String:
	if DIFFICULTY_SCRIPTS.has(d):
		return d
	push_warning("難度「%s」不是 easy／normal／hard，改用 normal" % d)
	return "normal"

static func enemy_path_for(difficulty_: String) -> String:
	return DIFFICULTY_SCRIPTS[normalize_difficulty(difficulty_)]

## 開局清掉資料夾裡上一場的快照與結果，回放才不會拼到舊場次。
func _clear_out_dir() -> void:
	if out_dir == "":
		return
	var real := ProjectSettings.globalize_path(out_dir)
	if not DirAccess.dir_exists_absolute(real):
		DirAccess.make_dir_recursive_absolute(real)
		return
	for f in DirAccess.get_files_at(real):
		if (f.begins_with("t") and f.ends_with(".json")) or f == "result.json" or f.ends_with(".tmp"):
			DirAccess.remove_absolute(real.path_join(f))

## 每個物理 tick 呼叫：回合邊界先下令、改天氣，再推進。
func tick(dt: float) -> void:
	if finished:
		return
	var turn := int(floor(orbat.t / TURN_SECONDS + 1e-6)) + 1
	while next_turn <= turn and next_turn <= MAX_TURNS:
		_start_turn(next_turn)
		next_turn += 1
	orbat.advance(dt)

func _start_turn(n: int) -> void:
	var key := str(n)
	var wx: String = str(enemy.get("weather_changes", {}).get(key, ""))
	var tod: String = str(enemy.get("time_changes", {}).get(key, ""))
	if wx != "" or tod != "":
		orbat.set_conditions(wx, tod)
	orbat.apply_orders("us", _orders(friendly, key))
	orbat.apply_orders("enemy", _orders(enemy, key))

func _orders(script: Dictionary, key: String) -> Array:
	var out: Array = []
	for d in script.get("orders", {}).get(key, []):
		out.append(Order.from_dict(d))
	return out

func _on_second(sec: int) -> void:
	if finished:
		return
	if sec % int(TURN_SECONDS) == 0:
		_snapshot(int(sec / TURN_SECONDS))
	for side in ["us", "enemy"]:
		if initial[side] > 0.0 and orbat.total_strength(side) < END_STRENGTH_RATIO * initial[side]:
			end_reason = "strength"
	if end_reason == "" and sec >= int(TURN_SECONDS) * MAX_TURNS:
		end_reason = "turns"
	if end_reason != "":
		_finish()

func _snapshot(n: int) -> void:
	if out_dir == "" or writer == null:
		return
	writer.update(orbat.second())   # 保險：正常情況 hook 順序已讓它更新過
	if writer.write(out_dir.path_join("t%d.json" % n)):
		snapshots += 1

func scores() -> Array[int]:
	var su := 0
	var se := 0
	for oid in orbat.map.objectives.keys():
		var o: Dictionary = orbat.map.objectives[oid]
		if o["owner"] == "us":
			su += int(o["value"])
		elif o["owner"] == "enemy":
			se += int(o["value"])
	return [su, se]

func _finish() -> void:
	finished = true
	if orbat.second() % int(TURN_SECONDS) != 0:
		_snapshot(int(ceil(orbat.second() / TURN_SECONDS)))   # 提早結束：最後一份快照＝結束那秒（檔名＝turns_played）
	var sc := scores()
	var stu := orbat.total_strength("us")
	var ste := orbat.total_strength("enemy")
	var winner := "draw"
	if sc[0] != sc[1]:
		winner = "us" if sc[0] > sc[1] else "enemy"
	elif absf(stu - ste) > 1e-9:
		winner = "us" if stu > ste else "enemy"
	result = {"battle_id": writer.battle_id if writer else "", "difficulty": difficulty, "turns_played": int(ceil(orbat.second() / TURN_SECONDS)),
		"seconds": orbat.second(), "end_reason": end_reason, "winner": winner, "score_us": sc[0], "score_enemy": sc[1],
		"strength_us": snappedf(stu, 0.001), "strength_enemy": snappedf(ste, 0.001)}
	if out_dir != "":
		var real := ProjectSettings.globalize_path(out_dir.path_join("result.json"))
		var f := FileAccess.open(real, FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(result, "  "))
			f.close()

func summary() -> String:
	if not finished:
		return ""
	var w: String = {"us": "我方勝", "enemy": "敵方勝", "draw": "平手"}[result["winner"]]
	var why: String = {"turns": "5 分鐘打完", "strength": "一方戰力低於初始 30%"}[result["end_reason"]]
	return "結果：%s（%s，%d 秒）｜據點分 我 %d : 敵 %d｜剩餘總戰力 我 %.2f : 敵 %.2f" % [w, why, result["seconds"], result["score_us"], result["score_enemy"], result["strength_us"], result["strength_enemy"]]

## 直接跑到結束（無頭測試與工具用）。
func run_to_end(dt: float = 1.0 / 60.0) -> Dictionary:
	var guard := 0
	while not finished and guard < 100000:
		tick(dt)
		guard += 1
	if not finished:
		push_error("會戰在 %d tick 內沒有結束" % guard)
	return result
