extends SceneTree
## 施工單 14 煙霧測試：攻擊劇本（orders_v1_assault.json）對三個難度各打完一場 5 分鐘會戰，
## 勝負與據點分必須與 docs/10 §14 的 M0 平衡表同趨勢（easy 勝 8:3、normal 勝 8:3、hard 敗 3:8）；
## 另驗結束原因、快照數、result.json 欄位、劇本排程（第 3 回合轉雨在第 60 秒）。
##   godot --headless --path . -s tests/smoke_battle.gd

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 24, 600.0)
	_run.call_deferred()

func play(difficulty: String, out_dir: String) -> Battle:
	var scene: PackedScene = load("res://scenes/Battle.tscn")
	var battle: Battle = scene.instantiate()
	battle.auto_advance = false
	battle.use_cmdline_args = false
	battle.board_out = ""
	battle.friendly_path = "m0://samples/orders_v1_assault.json"
	battle.difficulty = difficulty
	battle.snapshot_dir = out_dir
	get_root().add_child(battle)
	await process_frame
	await physics_frame
	await physics_frame
	battle.director.run_to_end()
	battle.show_result()
	return battle

func wipe(dir: String) -> void:
	var real := ProjectSettings.globalize_path(dir)
	if DirAccess.dir_exists_absolute(real):
		for sub in DirAccess.get_directories_at(real):
			for f in DirAccess.get_files_at(real.path_join(sub)):
				DirAccess.remove_absolute(real.path_join(sub).path_join(f))
			DirAccess.remove_absolute(real.path_join(sub))
		for f in DirAccess.get_files_at(real):
			DirAccess.remove_absolute(real.path_join(f))

## 小戰情板：5 個步兵排對 2 個步兵排全在 C3 → 約 40～60 秒敵方戰力 < 30% 提早結束。
func mini_battle(out_dir: String) -> Director:
	var sectors := {}
	for r in 5:
		for c in 5:
			var sid := SectorMap.id_of(c, r)
			sectors[sid] = {"id": sid, "terrain": "open", "cover": 0.2}
	var units: Array = []
	for i in 5:
		units.append({"id": "u%d" % i, "name": "u%d" % i, "echelon": "platoon", "type": "infantry", "parent": null, "strength": 1.0, "state": "idle", "sector": "C3", "task": {"type": "hold", "target": "C3"}})
	var board := {"schema_version": "0.2", "battle_id": "mini", "t": 0, "era": "ww2_1944", "weather": "clear", "time_of_day": "day",
		"map": {"cols": 5, "rows": 5, "sectors": sectors}, "orbat": units, "objectives": [], "events": []}
	var enemy := {"units": [
		{"id": "e1", "name": "e1", "echelon": "platoon", "type": "infantry", "parent": null, "strength": 1.0, "state": "idle", "sector": "C3", "task": {"type": "hold", "target": "C3"}},
		{"id": "e2", "name": "e2", "echelon": "platoon", "type": "infantry", "parent": null, "strength": 1.0, "state": "idle", "sector": "C3", "task": {"type": "hold", "target": "C3"}}],
		"orders": {"1": [{"unit_id": "e1", "task": "hold", "target": "Z9"}], "11": [{"unit_id": "e2", "task": "seize", "target": "A1"}]}}
	var map := SectorMap.new()
	get_root().add_child(map)
	map.build_from_board(board)
	var o := Orbat.new()
	get_root().add_child(o)
	o.setup(map, Rules.load_era())
	o.build(board, enemy["units"])
	var w := BoardWriter.new(o, "mini", "ww2_1944")
	o.second_hooks.append(w.update)
	w.update(0)
	return Director.new(o, w, {}, enemy, "normal", out_dir)

func _run() -> void:
	wipe("user://smoke_battle")
	# ---- 導演單元檢查：提早結束、壞命令、第 11 回合忽略、不寫檔、未知難度、舊檔清除 ----
	var d0 := mini_battle("")
	var r0 := d0.run_to_end()
	h.check(r0["end_reason"] == "strength" and r0["seconds"] > 30 and r0["seconds"] < 120 and d0.snapshots == 0, "戰力提早結束（%d 秒）；out_dir 空就不寫快照" % r0["seconds"])
	h.check(d0.orbat.events.any(func(ev: Dictionary) -> bool: return ev["kind"] == "info" and ev["text"].contains("退回")), "劇本裡的壞命令 → info 事件、不影響其他命令")
	h.check(d0.orbat.platoons["e2"].task != {"type": "seize", "target": "A1"}, "第 11 回合的命令被忽略")
	var stale := ProjectSettings.globalize_path("user://smoke_battle/mini")
	DirAccess.make_dir_recursive_absolute(stale)
	for n in [7, 8, 9, 10]:
		var f := FileAccess.open(stale.path_join("t%d.json" % n), FileAccess.WRITE)
		f.store_string("{}")
		f.close()
	var d1 := mini_battle("user://smoke_battle/mini")
	var r1 := d1.run_to_end()
	var files: Array = Array(DirAccess.get_files_at(stale))
	files.sort()
	var last_n := int(ceil(r1["seconds"] / 30.0))
	h.check(not files.has("t10.json") and files.has("t0.json") and files.has("t%d.json" % last_n) and files.has("result.json"), "開局清掉舊快照；提早結束補最後一份 t%d.json（＝turns_played）" % last_n)
	h.check(r1["turns_played"] == last_n and d1.snapshots == last_n + 1, "turns_played 與最後快照編號一致")
	var last_board: Variant = JSON.parse_string(FileAccess.get_file_as_string(stale.path_join("t%d.json" % last_n)))
	h.check(last_board["t"] == r1["seconds"] and last_board["events"].size() == d1.orbat.events.size(), "最後快照＝結束那秒，事件一筆不少")
	print("  （下面一個 WARNING 是故意的：未知難度）")
	h.check(Director.normalize_difficulty("insane") == "normal" and Director.enemy_path_for("hard").ends_with("enemy_v1_hard.json"), "未知難度退回 normal 並警告；已知難度對應劇本")
	var expect := {"easy": ["us", 8, 3], "normal": ["us", 8, 3], "hard": ["enemy", 3, 8]}
	for d in ["easy", "normal", "hard"]:
		var b := await play(d, "user://smoke_battle")
		var r: Dictionary = b.director.result
		var e: Array = expect[d]
		h.check(r["winner"] == e[0] and r["score_us"] == e[1] and r["score_enemy"] == e[2], "%s：%s %d:%d（§14 同趨勢）" % [d, "我方勝" if e[0] == "us" else "敵方勝", e[1], e[2]])
		h.check(r["end_reason"] == "turns" and r["seconds"] == 300 and r["turns_played"] == 10, "%s：5 分鐘打完、10 回合" % d)
		h.check(b.director.snapshots == 11 and FileAccess.file_exists(ProjectSettings.globalize_path("user://smoke_battle/hill-town-start-%s/t10.json" % d)) and FileAccess.file_exists(ProjectSettings.globalize_path("user://smoke_battle/hill-town-start-%s/result.json" % d)), "%s：t0～t10 共 11 份快照與 result.json（開跑前已清空資料夾）" % d)
		h.check(b.hud_label.text.contains("已結束") and b.difficulty == d, "%s：結束後 HUD 顯示已結束" % d)
		if d == "normal":
			var wx := b.orbat.events.filter(func(ev: Dictionary) -> bool: return ev["kind"] == "weather")
			h.check(wx.size() == 3 and wx[0]["text"] == "天氣轉雨" and wx[0]["t"] == 60 and wx[1]["text"] == "進入夜間" and wx[1]["t"] == 150 and wx[2]["text"] == "天氣轉霧" and wx[2]["t"] == 210, "normal 劇本：第 3 回合（60 秒）轉雨、第 6 回合（150 秒）入夜、第 8 回合（210 秒）起霧")
			h.check(b.orbat.events.any(func(ev: Dictionary) -> bool: return ev["kind"] == "order" and ev["t"] == 0 and ev["text"].begins_with("參謀長令 A5 迫砲排 固守 B3")), "我方劇本第 1 回合的命令在第 0 秒下達")
			h.check(b.orbat.events.any(func(ev: Dictionary) -> bool: return ev["kind"] == "seized" and ev["sector"] == "C3" and ev["text"].begins_with("我方取得 C3")), "normal：城鎮 C3 易手")
			h.check(b.get_node_or_null("HUD/Result") != null and b.director.summary().begins_with("結果：我方勝"), "結果畫面與摘要")
			h.check(r["strength_us"] > 6.0 and r["strength_enemy"] > 3.5 and r["strength_enemy"] < 5.0, "normal 剩餘戰力與 M0（6.64:4.15）同量級")
		b.queue_free()
		await process_frame
	h.finish()
