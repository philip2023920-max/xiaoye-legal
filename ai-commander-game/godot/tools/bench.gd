extends SceneTree
## 無頭 CPU 基準（施工單 15）：把均衡範本＋normal 敵軍複製 N 倍（每倍 14 個排、126 人），全部下「奪取 C3」，
## 推進 60 秒，印每個物理 tick 的平均毫秒（預算：60 Hz 下 16.7 ms；目標 1 倍 < 2 ms）。
##   godot --headless --path . -s tools/bench.gd -- scales=1,5,10 max_ms=16
func _initialize() -> void:
	create_timer(900.0).timeout.connect(func() -> void:
		printerr("逾時 900 秒")
		quit(2))
	_run.call_deferred()

func build(scale: int) -> Orbat:
	var board := BoardIO.load_board("m0://samples/board_deployed_balanced.json")
	var enemy := BoardIO.load_json("m0://samples/enemy_script_v1.json")
	var map := SectorMap.new()
	get_root().add_child(map)
	map.build_from_board(board)
	var o := Orbat.new()
	get_root().add_child(o)
	o.setup(map, Rules.load_era())
	var us: Array = []
	var en: Array = []
	for k in scale:
		for u in board["orbat"]:
			var d: Dictionary = u.duplicate(true)
			if k > 0:
				d["id"] = "%s-%d" % [d["id"], k]
				if d.get("parent") != null:
					d["parent"] = "%s-%d" % [d["parent"], k]
			us.append(d)
		for u in enemy["units"]:
			var d: Dictionary = u.duplicate(true)
			if k > 0:
				d["id"] = "%s-%d" % [d["id"], k]
				if d.get("parent") != null:
					d["parent"] = "%s-%d" % [d["parent"], k]
			en.append(d)
	var b := board.duplicate(true)
	b["orbat"] = us
	o.build(b, en)
	var orders: Array = []
	for cid in o.companies.keys():
		if o.companies[cid]["side"] == "us":
			orders.append(Order.make(cid, "seize", "C3", "player"))
	o.apply_orders("us", orders)
	return o

func _run() -> void:
	var scales: Array = [1, 5]
	var max_ms := 0.0
	for a in OS.get_cmdline_user_args():
		if a.begins_with("scales="):
			scales = Array(a.trim_prefix("scales=").split(",")).map(func(s: String) -> int: return int(s))
		elif a.begins_with("max_ms="):
			max_ms = float(a.trim_prefix("max_ms="))
	var worst := 0.0
	print("倍數  排數  人數   平均 ms/tick   最大 ms/tick（60 秒、3600 tick）")
	for scale in scales:
		var o := build(int(scale))
		var ticks := 3600
		var t0 := Time.get_ticks_usec()
		var slowest := 0.0
		for i in ticks:
			var a := Time.get_ticks_usec()
			o.advance(1.0 / 60.0)
			slowest = maxf(slowest, (Time.get_ticks_usec() - a) / 1000.0)
		var avg := (Time.get_ticks_usec() - t0) / 1000.0 / ticks
		print("%4d  %4d  %5d   %8.3f       %8.3f" % [int(scale), o.platoons.size(), o.total_soldiers("us") + o.total_soldiers("enemy"), avg, slowest])
		if int(scale) == 1:
			worst = avg
		o.queue_free()
		await process_frame
	if max_ms > 0.0 and worst > max_ms:
		printerr("1 倍的平均 %.3f ms 超過上限 %.1f ms" % [worst, max_ms])
		quit(1)
		return
	quit(0)
