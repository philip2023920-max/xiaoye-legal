extends SceneTree
## 無頭 CPU 基準（施工單 15）：把均衡範本＋normal 敵軍複製 N 倍（每倍 14 個排、126 人；同一戰情板複製，站位會重疊），
## 全部下「奪取 C3」，推進 60 秒，印每個物理 tick 的平均／p99／最大毫秒。含每秒的戰情板歸屬與敵情更新（BoardWriter.update），
## 不含每 0.1 秒的 JSON 寫檔與畫面。預算：60 Hz 下 16.7 ms。
##   godot --headless --path . -s tools/bench.gd -- scales=1,5,10 max_ms=8
func _initialize() -> void:
	create_timer(900.0).timeout.connect(func() -> void:
		printerr("逾時 900 秒")
		quit(2))
	_run.call_deferred()

## 建一個 scale 倍的會戰，掛在 root 底下；回傳 [Orbat, SectorMap]。
static func build(root: Node, scale: int) -> Array:
	var board := BoardIO.load_board("m0://samples/board_deployed_balanced.json")
	var enemy := BoardIO.load_json("m0://samples/enemy_script_v1.json")
	var map := SectorMap.new()
	root.add_child(map)
	map.build_from_board(board)
	var o := Orbat.new()
	root.add_child(o)
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
	var writer := BoardWriter.new(o, "bench", "ww2_1944")
	o.second_hooks.append(writer.update)
	writer.update(0)
	o.set_meta("writer", writer)   # 讓 hook 的目標活著
	var orders: Array = []
	for cid in o.companies.keys():
		if o.companies[cid]["side"] == "us":
			orders.append(Order.make(cid, "seize", "C3", "player"))
	o.apply_orders("us", orders)
	return [o, map]

## 推進 ticks 個 tick，回傳 {avg, p99, max, soldiers}（剔除第 0 tick：同時下令與暖機）。
static func measure(o: Orbat, ticks: int) -> Dictionary:
	var samples := PackedFloat64Array()
	for i in ticks:
		var a := Time.get_ticks_usec()
		o.advance(1.0 / 60.0)
		if i > 0:
			samples.append((Time.get_ticks_usec() - a) / 1000.0)
	var sorted := samples.duplicate()
	sorted.sort()
	var total := 0.0
	for v in samples:
		total += v
	return {"avg": total / samples.size(), "p99": sorted[int(floor(sorted.size() * 0.99))], "max": sorted[sorted.size() - 1],
		"soldiers": o.total_soldiers("us") + o.total_soldiers("enemy")}

func _run() -> void:
	var scales: Array = [1, 5]
	var max_ms := 0.0
	for a in OS.get_cmdline_user_args():
		if a.begins_with("scales="):
			scales = Array(a.trim_prefix("scales=").split(",")).map(func(s: String) -> int: return int(s))
		elif a.begins_with("max_ms="):
			max_ms = float(a.trim_prefix("max_ms="))
	var first_avg := -1.0
	print("倍數  排數  人數   平均 ms/tick   p99 ms/tick   最大 ms/tick（60 秒、3600 tick，剔除 tick 0）")
	for scale in scales:
		var built := build(get_root(), int(scale))
		var o: Orbat = built[0]
		var r := measure(o, 3600)
		print("%4d  %4d  %5d   %8.3f       %8.3f      %8.3f" % [int(scale), o.platoons.size(), r["soldiers"], r["avg"], r["p99"], r["max"]])
		if first_avg < 0.0:
			first_avg = r["avg"]
		o.queue_free()
		built[1].queue_free()
		await process_frame
	if max_ms > 0.0 and first_avg > max_ms:
		printerr("第一個倍數的平均 %.3f ms 超過上限 %.1f ms" % [first_avg, max_ms])
		quit(1)
		return
	quit(0)
