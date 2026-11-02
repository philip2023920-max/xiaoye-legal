extends SceneTree
## 施工單 14 煙霧測試：攻擊劇本（orders_v1_assault.json）對三個難度各打完一場 5 分鐘會戰，
## 勝負與據點分必須與 docs/10 §14 的 M0 平衡表同趨勢（easy 勝 8:3、normal 勝 8:3、hard 敗 3:8）；
## 另驗結束原因、快照數、result.json 欄位、劇本排程（第 3 回合轉雨在第 60 秒）。
##   godot --headless --path . -s tests/smoke_battle.gd

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 14, 600.0)
	_run.call_deferred()

func play(difficulty: String, out_dir: String) -> Battle:
	var scene: PackedScene = load("res://scenes/Battle.tscn")
	var battle: Battle = scene.instantiate()
	battle.auto_advance = false
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

func _run() -> void:
	var expect := {"easy": ["us", 8, 3], "normal": ["us", 8, 3], "hard": ["enemy", 3, 8]}
	for d in ["easy", "normal", "hard"]:
		var b := await play(d, "user://smoke_battle")
		var r: Dictionary = b.director.result
		var e: Array = expect[d]
		h.check(r["winner"] == e[0] and r["score_us"] == e[1] and r["score_enemy"] == e[2], "%s：%s %d:%d（§14 同趨勢）" % [d, "我方勝" if e[0] == "us" else "敵方勝", e[1], e[2]])
		h.check(r["end_reason"] == "turns" and r["seconds"] == 300 and r["turns_played"] == 10, "%s：5 分鐘打完、10 回合" % d)
		h.check(b.director.snapshots == 11 and FileAccess.file_exists(ProjectSettings.globalize_path("user://smoke_battle/hill-town-start-%s/t10.json" % d)) and FileAccess.file_exists(ProjectSettings.globalize_path("user://smoke_battle/hill-town-start-%s/result.json" % d)), "%s：t0～t10 共 11 份快照與 result.json" % d)
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
