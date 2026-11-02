extends SceneTree
## 無頭跑完一場 5 分鐘會戰，寫快照與結果（給 M0 的 chief replay 與 Python 測試用）。
##   godot --headless --path . -s tools/run_battle.gd -- difficulty=normal friendly=m0://samples/orders_v1_assault.json out_dir=/abs/dir
func _initialize() -> void:
	create_timer(600.0).timeout.connect(func() -> void:
		printerr("逾時 600 秒：會戰沒有跑完（看上面的 SCRIPT ERROR）")
		quit(2))
	_run.call_deferred()

func _run() -> void:
	var difficulty := "normal"
	var friendly_path := "m0://samples/orders_v1_assault.json"
	var out_dir := ""
	var board_path := "m0://samples/board_deployed_balanced.json"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("difficulty="):
			difficulty = a.trim_prefix("difficulty=")
		elif a.begins_with("friendly="):
			friendly_path = a.trim_prefix("friendly=")
		elif a.begins_with("out_dir="):
			out_dir = a.trim_prefix("out_dir=")
		elif a.begins_with("board="):
			board_path = a.trim_prefix("board=")
	if not Director.DIFFICULTY_SCRIPTS.has(difficulty):
		printerr("難度「%s」不是 easy／normal／hard" % difficulty)
		quit(1)
		return
	var scene: PackedScene = load("res://scenes/Battle.tscn")
	var battle: Battle = scene.instantiate()
	battle.auto_advance = false
	battle.use_cmdline_args = false
	battle.board_out = ""
	battle.board_path = board_path
	battle.friendly_path = friendly_path
	battle.difficulty = difficulty
	battle.snapshot_dir = out_dir
	get_root().add_child(battle)
	await process_frame
	await physics_frame
	await physics_frame
	if battle.director == null:
		printerr("場景沒有建立導演（開局戰情板或劇本載入失敗）")
		quit(1)
		return
	if battle.enemy_script.is_empty() or (friendly_path != "" and battle.friendly_script.is_empty()):
		printerr("劇本載入失敗：enemy=%s friendly=%s" % [battle.enemy_path, friendly_path])
		quit(1)
		return
	var r := battle.director.run_to_end()
	if r.is_empty():
		printerr("會戰沒有結束")
		quit(1)
		return
	battle.show_result()
	print(battle.director.summary())
	print("difficulty=%s winner=%s score=%d:%d end=%s seconds=%d snapshots=%d" % [difficulty, r["winner"], r["score_us"], r["score_enemy"], r["end_reason"], r["seconds"], battle.director.snapshots])
	quit(0)
