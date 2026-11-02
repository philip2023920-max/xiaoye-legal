extends SceneTree
## 無頭跑一段會戰並把戰情板寫到指定路徑（給 Python 合約測試與範例檔用）。
##   godot --headless --path . -s tools/dump_board.gd -- out=/abs/path/board.json seconds=120
## 開局先下「A 連 奪取 C3」讓它有接觸、歸屬變化與交火。
func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var out := ""
	var seconds := 120.0
	for a in OS.get_cmdline_user_args():
		if a.begins_with("out="):
			out = a.trim_prefix("out=")
		elif a.begins_with("seconds="):
			seconds = float(a.trim_prefix("seconds="))
	if out == "":
		printerr("用法：-- out=<路徑> [seconds=120]")
		quit(1)
		return
	var scene: PackedScene = load("res://scenes/Battle.tscn")
	var battle: Battle = scene.instantiate()
	battle.auto_advance = false
	battle.board_out = ""
	get_root().add_child(battle)
	await process_frame
	await physics_frame
	await physics_frame
	battle.orbat.apply_orders("us", [Order.make("co-A", "seize", "C3", "player", "dump")])
	battle.orbat.advance_for(seconds)
	var ok := battle.writer.write(out)
	print("board written: %s ok=%s t=%d events=%d contacts=%d" % [out, ok, int(battle.orbat.t), battle.orbat.events.size(), battle.writer.contacts.size()])
	quit(0 if ok else 1)
